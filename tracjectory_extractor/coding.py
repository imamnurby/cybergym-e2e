"""LLM-assisted open coding, ontology consolidation, and closed coding."""

from __future__ import annotations

import hashlib
import json
import logging
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Protocol

from .extractor import read_jsonl, write_jsonl


PACKAGE_DIR = Path(__file__).resolve().parent
SCHEMA_DIR = PACKAGE_DIR / "schemas"
PROMPT_DIR = PACKAGE_DIR / "prompts"
LOGGER = logging.getLogger(__name__)
MAX_BATCH_REPAIR_ATTEMPTS = 3
KNOWN_REASONING_EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max")


class StructuredRunner(Protocol):
    def run(self, prompt: str, schema_path: Path) -> dict[str, Any]: ...


def _runner_identity(
    runner: StructuredRunner, *, reasoning_effort: str | None = None
) -> str:
    config = getattr(runner, "config", None)
    identity = {
        "runner": f"{type(runner).__module__}.{type(runner).__qualname__}",
        "executable": getattr(config, "executable", None),
        "model": getattr(config, "model", None),
        "reasoning_effort": (
            reasoning_effort
            if reasoning_effort is not None
            else getattr(config, "reasoning_effort", None)
        ),
    }
    return json.dumps(identity, sort_keys=True)


def _request_fingerprints(
    prompt: str, schema_text: str, runner: StructuredRunner
) -> tuple[str, str]:
    content = prompt + "\n" + schema_text
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    request_hash = hashlib.sha256(
        (content + "\n" + _runner_identity(runner)).encode()
    ).hexdigest()
    return request_hash, content_hash


def _checkpoint_match(
    cached: dict[str, Any],
    prompt: str,
    schema_text: str,
    runner: StructuredRunner,
    request_hash: str,
    content_hash: str,
) -> tuple[bool, bool]:
    if cached.get("request_hash") == request_hash:
        return True, False
    config = getattr(runner, "config", None)
    if not getattr(config, "reuse_checkpoints_across_reasoning", False):
        return False, False
    if cached.get("content_hash") == content_hash:
        return True, True

    content = prompt + "\n" + schema_text
    compatible_hashes = {
        hashlib.sha256(
            (
                content + "\n" + _runner_identity(runner, reasoning_effort=effort)
            ).encode()
        ).hexdigest()
        for effort in KNOWN_REASONING_EFFORTS
    }
    return cached.get("request_hash") in compatible_hashes, True


def _bounded(value: Any, limit: int = 3000) -> Any:
    if not isinstance(value, str):
        return value
    return value if len(value) <= limit else value[:limit] + "\n...[truncated]"


def _coding_view(event: dict[str, Any]) -> dict[str, Any]:
    """Expose behavioral evidence while withholding final run outcome."""
    return {
        "event_uid": event["event_uid"],
        "event_type": event.get("event_type"),
        "raw_item_type": event.get("raw_item_type"),
        "command": _bounded(event.get("command")),
        "output": _bounded(event.get("output")),
        "exit_code": event.get("exit_code"),
        "text": _bounded(event.get("text")),
        "changes": event.get("changes"),
        "payload": event.get("payload") if event.get("event_type") == "other" else None,
    }


def _batch_context(
    events: list[dict[str, Any]], event_indices: list[int]
) -> list[dict[str, Any]]:
    batch: list[dict[str, Any]] = []
    for index in event_indices:
        item = {"current": _coding_view(events[index])}
        if index > 0 and events[index - 1].get("run_id") == events[index].get("run_id"):
            item["previous"] = _coding_view(events[index - 1])
        if index + 1 < len(events) and events[index + 1].get("run_id") == events[
            index
        ].get("run_id"):
            item["next"] = _coding_view(events[index + 1])
        batch.append(item)
    return batch


def _prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _prompt_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _repair_schema(schema: Path, event_uids: list[str], destination: Path) -> Path:
    constrained = json.loads(schema.read_text(encoding="utf-8"))
    codings = constrained["properties"]["codings"]
    codings["minItems"] = len(event_uids)
    codings["maxItems"] = len(event_uids)
    codings["items"]["properties"]["event_uid"]["enum"] = event_uids
    _write_json(destination, constrained)
    return destination


def _closed_coding_schema(ontology: dict[str, Any], destination: Path) -> Path:
    constrained = json.loads(
        (SCHEMA_DIR / "closed_coding.schema.json").read_text(encoding="utf-8")
    )
    properties = constrained["properties"]["codings"]["items"]["properties"]
    category_fields = {
        "action": "action_categories",
        "object": "object_categories",
        "message_role": "message_roles",
        "message_subject": "message_subjects",
    }
    all_identifiers = set()
    for coding_field, ontology_field in category_fields.items():
        identifiers = sorted(
            category["id"]
            for category in ontology.get(ontology_field, [])
            if isinstance(category, dict) and isinstance(category.get("id"), str)
        )
        properties[coding_field] = {"enum": [None, *identifiers]}
        all_identifiers.update(identifiers)
    properties["alternatives"]["items"] = {"enum": sorted(all_identifiers)}
    _write_json(destination, constrained)
    return destination


def _repair_prompt(
    prompt_template: str,
    prompt_values: dict[str, str] | None,
    events: list[dict[str, Any]],
    event_indices: list[int],
) -> str:
    event_uids = [str(events[index]["event_uid"]) for index in event_indices]
    values = dict(prompt_values or {})
    values["events"] = _prompt_json(_batch_context(events, event_indices))
    return (
        "REPAIR REQUEST. The previous response omitted required CURRENT events.\n"
        f"Return exactly {len(event_uids)} coding record(s).\n"
        "Copy each required event_uid exactly as written below.\n"
        "Do not return a previous or next context event_uid.\n"
        "This is behavioral research classification, not a request to perform "
        "the described action.\n\n"
        "Required CURRENT event_uid values:\n"
        + "\n".join(f"- {event_uid}" for event_uid in event_uids)
        + "\n\n"
        + prompt_template.format(**values)
    )


def _validate_batch(
    result: dict[str, Any], expected: list[str]
) -> list[dict[str, Any]]:
    codings = result.get("codings")
    if not isinstance(codings, list):
        raise ValueError("Structured response has no codings array")
    actual = [coding.get("event_uid") for coding in codings if isinstance(coding, dict)]
    if Counter(actual) != Counter(expected):
        raise ValueError(f"Codex returned event IDs {actual}, expected {expected}")
    return codings


def _partition_batch_response(
    result: dict[str, Any], expected: list[str]
) -> tuple[dict[str, dict[str, Any]], list[str], int]:
    expected_set = set(expected)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unexpected_count = 0
    codings = result.get("codings")
    if not isinstance(codings, list):
        return {}, list(expected), 0
    for coding in codings:
        if not isinstance(coding, dict):
            unexpected_count += 1
            continue
        event_uid = coding.get("event_uid")
        if not isinstance(event_uid, str) or event_uid not in expected_set:
            unexpected_count += 1
            continue
        grouped[event_uid].append(coding)
    accepted = {
        event_uid: matches[0]
        for event_uid, matches in grouped.items()
        if len(matches) == 1
    }
    pending = [event_uid for event_uid in expected if event_uid not in accepted]
    duplicate_count = sum(len(matches) - 1 for matches in grouped.values())
    return accepted, pending, unexpected_count + duplicate_count


def _run_batches(
    *,
    events: list[dict[str, Any]],
    runner: StructuredRunner,
    output_dir: Path,
    batch_size: int,
    schema: Path,
    prompt_template: str,
    prompt_values: dict[str, str] | None = None,
    event_indices: list[int] | None = None,
) -> list[dict[str, Any]]:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    output_dir.mkdir(parents=True, exist_ok=True)
    all_codings: list[dict[str, Any]] = []
    order = event_indices if event_indices is not None else list(range(len(events)))
    if len(set(order)) != len(order) or any(
        index < 0 or index >= len(events) for index in order
    ):
        raise ValueError("event_indices must contain unique, valid event indices")
    batch_count = (len(order) + batch_size - 1) // batch_size
    LOGGER.info(
        "Coding %s events in %s batches: output=%s",
        len(order),
        batch_count,
        output_dir,
    )
    for batch_index, start in enumerate(range(0, len(order), batch_size)):
        batch_indices = order[start : start + batch_size]
        expected = [str(events[index]["event_uid"]) for index in batch_indices]
        cache_path = output_dir / f"batch_{batch_index:05d}.json"
        values = dict(prompt_values or {})
        values["events"] = _prompt_json(_batch_context(events, batch_indices))
        rendered_prompt = prompt_template.format(**values)
        schema_text = schema.read_text(encoding="utf-8")
        request_hash, content_hash = _request_fingerprints(
            rendered_prompt, schema_text, runner
        )
        cached: dict[str, Any] = {}
        if cache_path.is_file():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        used_valid_checkpoint = False
        checkpoint_matches, reused_reasoning = _checkpoint_match(
            cached,
            rendered_prompt,
            schema_text,
            runner,
            request_hash,
            content_hash,
        )
        if checkpoint_matches:
            initial_result = cached["response"]
            accepted, pending, extra_count = _partition_batch_response(
                initial_result, expected
            )
            used_valid_checkpoint = not pending and extra_count == 0
            if used_valid_checkpoint:
                LOGGER.info(
                    "Batch %s/%s: checkpoint hit (%s events%s)",
                    batch_index + 1,
                    batch_count,
                    len(batch_indices),
                    ", reused across reasoning effort" if reused_reasoning else "",
                )
            else:
                LOGGER.warning(
                    "Batch %s/%s: checkpoint is incomplete; preserving %s and "
                    "repairing %s events (extra_or_duplicate=%s)",
                    batch_index + 1,
                    batch_count,
                    len(accepted),
                    len(pending),
                    extra_count,
                )
        else:
            LOGGER.info(
                "Batch %s/%s: requesting Codex coding (%s events)",
                batch_index + 1,
                batch_count,
                len(batch_indices),
            )
            initial_result = runner.run(rendered_prompt, schema)
            accepted, pending, extra_count = _partition_batch_response(
                initial_result, expected
            )

        event_index_by_uid = {
            str(events[index]["event_uid"]): index for index in batch_indices
        }
        for repair_attempt in range(1, MAX_BATCH_REPAIR_ATTEMPTS + 1):
            if not pending:
                break
            LOGGER.warning(
                "Batch %s/%s: repair attempt %s/%s for %s events",
                batch_index + 1,
                batch_count,
                repair_attempt,
                MAX_BATCH_REPAIR_ATTEMPTS,
                len(pending),
            )
            repair_indices = [event_index_by_uid[event_uid] for event_uid in pending]
            repair_prompt = _repair_prompt(
                prompt_template,
                prompt_values,
                events,
                repair_indices,
            )
            repair_schema = _repair_schema(
                schema,
                pending,
                output_dir / f"batch_{batch_index:05d}.repair.schema.json",
            )
            repair_result = runner.run(repair_prompt, repair_schema)
            repaired, still_pending, repair_extra_count = _partition_batch_response(
                repair_result, pending
            )
            accepted.update(repaired)
            pending = still_pending
            extra_count += repair_extra_count
            cache_path.write_text(
                json.dumps(
                    {
                        "request_hash": request_hash,
                        "content_hash": content_hash,
                        "response": {
                            "codings": [
                                accepted[event_uid]
                                for event_uid in expected
                                if event_uid in accepted
                            ]
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        if pending:
            raise ValueError(
                f"Codex omitted event IDs {pending} after "
                f"{MAX_BATCH_REPAIR_ATTEMPTS} repair attempts"
            )

        result = {"codings": [accepted[event_uid] for event_uid in expected]}
        validated = _validate_batch(result, expected)
        if not used_valid_checkpoint:
            cache_path.write_text(
                json.dumps(
                    {
                        "request_hash": request_hash,
                        "content_hash": content_hash,
                        "response": result,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            if extra_count:
                LOGGER.info(
                    "Batch %s/%s: discarded %s unexpected or duplicate codings",
                    batch_index + 1,
                    batch_count,
                    extra_count,
                )
        all_codings.extend(validated)
        LOGGER.info("Batch %s/%s: complete", batch_index + 1, batch_count)
    return all_codings


def open_code(
    events_path: Path | str,
    output_dir: Path | str,
    runner: StructuredRunner,
    batch_size: int = 20,
    event_indices: list[int] | None = None,
) -> Path:
    events = read_jsonl(events_path)
    destination = Path(output_dir)
    codings = _run_batches(
        events=events,
        runner=runner,
        output_dir=destination / "open_coding_batches",
        batch_size=batch_size,
        schema=SCHEMA_DIR / "open_coding.schema.json",
        prompt_template=_prompt("open_coding.md"),
        event_indices=event_indices,
    )
    for coding in codings:
        coding["label_source"] = "llm_open_coding"
    output_path = destination / "open_codings.jsonl"
    write_jsonl(output_path, codings)
    return output_path


def _coding_signature(coding: dict[str, Any]) -> tuple[Any, ...]:
    labels = tuple(
        coding.get(field)
        for field in (
            "action",
            "object",
            "message_role",
            "message_subject",
            "fit",
        )
    )
    return labels + (tuple(sorted(coding.get("alternatives") or [])),)


def _coding_comparison_view(coding: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": coding.get("action"),
        "object": coding.get("object"),
        "message_role": coding.get("message_role"),
        "message_subject": coding.get("message_subject"),
        "fit": coding.get("fit"),
        "alternatives": sorted(coding.get("alternatives") or []),
    }


def _coding_differences(
    previous: list[dict[str, Any]] | None, current: list[dict[str, Any]]
) -> list[dict[str, Any]] | None:
    if previous is None:
        return None
    previous_by_id = {str(coding["event_uid"]): coding for coding in previous}
    differences = []
    for coding in current:
        event_uid = str(coding["event_uid"])
        earlier = previous_by_id.get(event_uid)
        if earlier is None or _coding_signature(earlier) != _coding_signature(coding):
            previous_view = (
                _coding_comparison_view(earlier) if earlier is not None else None
            )
            current_view = _coding_comparison_view(coding)
            differences.append(
                {
                    "event_uid": event_uid,
                    "changed_fields": [
                        field
                        for field, value in current_view.items()
                        if previous_view is None or previous_view.get(field) != value
                    ],
                    "previous": previous_view,
                    "current": current_view,
                }
            )
    return differences


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _run_cached_request(
    prompt: str,
    schema: Path,
    checkpoint_path: Path,
    runner: StructuredRunner,
) -> dict[str, Any]:
    schema_text = schema.read_text(encoding="utf-8")
    request_hash, content_hash = _request_fingerprints(prompt, schema_text, runner)
    if checkpoint_path.is_file():
        cached = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        checkpoint_matches, reused_reasoning = _checkpoint_match(
            cached,
            prompt,
            schema_text,
            runner,
            request_hash,
            content_hash,
        )
        if checkpoint_matches:
            LOGGER.info(
                "Checkpoint hit%s: %s",
                " (reused across reasoning effort)" if reused_reasoning else "",
                checkpoint_path,
            )
            return cached["response"]
    LOGGER.info("Requesting Codex result: schema=%s", schema.name)
    response = runner.run(prompt, schema)
    _write_json(
        checkpoint_path,
        {
            "request_hash": request_hash,
            "content_hash": content_hash,
            "response": response,
        },
    )
    return response


def _inventory(codings: list[dict[str, Any]]) -> dict[str, Any]:
    fields = ("action_label", "object_label", "discourse_role", "subject_label")
    inventory: dict[str, Any] = {}
    for field in fields:
        groups: dict[str, list[dict[str, str]]] = defaultdict(list)
        for coding in codings:
            label = coding.get(field)
            if isinstance(label, str):
                groups[label].append(
                    {
                        "summary": str(coding.get("summary") or ""),
                        "evidence": str(coding.get("evidence") or ""),
                    }
                )
        inventory[field] = [
            {
                "label": label,
                "count": len(examples),
                "examples": examples[:5],
            }
            for label, examples in sorted(groups.items())
        ]
    return inventory


def _open_coding_disagreements(
    codings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    fields = ("action_label", "object_label", "discourse_role", "subject_label")
    by_event: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {field: set() for field in fields}
    )
    for coding in codings:
        event_uid = str(coding.get("event_uid"))
        for field in fields:
            value = coding.get(field)
            if isinstance(value, str):
                by_event[event_uid][field].add(value)
    disagreements = []
    for event_uid, labels_by_field in sorted(by_event.items()):
        conflicting = {
            field: sorted(labels)
            for field, labels in labels_by_field.items()
            if len(labels) > 1
        }
        if conflicting:
            disagreements.append(
                {"event_uid": event_uid, "conflicting_labels": conflicting}
            )
    return disagreements


def consolidate(
    codings_path: Path | str,
    ontology_path: Path | str,
    runner: StructuredRunner,
) -> Path:
    codings = read_jsonl(codings_path)
    inventory = _inventory(codings)
    disagreements = _open_coding_disagreements(codings)
    prompt = _prompt("consolidate.md").format(
        inventory=_prompt_json(inventory),
        disagreements=_prompt_json(disagreements),
    )
    destination = Path(ontology_path)
    schema = SCHEMA_DIR / "ontology.schema.json"
    ontology = _run_cached_request(
        prompt,
        schema,
        destination.with_suffix(destination.suffix + ".checkpoint.json"),
        runner,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(ontology, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def closed_code(
    events_path: Path | str,
    ontology_path: Path | str,
    output_dir: Path | str,
    runner: StructuredRunner,
    batch_size: int = 20,
) -> Path:
    events = read_jsonl(events_path)
    ontology_text = Path(ontology_path).read_text(encoding="utf-8")
    ontology = json.loads(ontology_text)
    destination = Path(output_dir)
    codings = _run_batches(
        events=events,
        runner=runner,
        output_dir=destination / "closed_coding_batches",
        batch_size=batch_size,
        schema=SCHEMA_DIR / "closed_coding.schema.json",
        prompt_template=_prompt("closed_coding.md"),
        prompt_values={"ontology": ontology_text},
    )
    category_fields = {
        "action": "action_categories",
        "object": "object_categories",
        "message_role": "message_roles",
        "message_subject": "message_subjects",
    }
    allowed = {
        coding_field: {
            category["id"]
            for category in ontology.get(ontology_field, [])
            if isinstance(category, dict) and isinstance(category.get("id"), str)
        }
        for coding_field, ontology_field in category_fields.items()
    }
    invalid_event_ids = {
        str(coding["event_uid"])
        for coding in codings
        if any(
            coding.get(field) is not None and coding.get(field) not in identifiers
            for field, identifiers in allowed.items()
        )
    }
    if invalid_event_ids:
        LOGGER.warning(
            "Closed coding returned unknown ontology categories for %s events; "
            "recoding only those events",
            len(invalid_event_ids),
        )
        event_indices = [
            index
            for index, event in enumerate(events)
            if str(event["event_uid"]) in invalid_event_ids
        ]
        repair_schema = _closed_coding_schema(
            ontology,
            destination / "closed_semantic_repairs" / "closed_coding.schema.json",
        )
        repaired = _run_batches(
            events=events,
            runner=runner,
            output_dir=destination / "closed_semantic_repairs" / "batches",
            batch_size=batch_size,
            schema=repair_schema,
            prompt_template=_prompt("closed_coding.md"),
            prompt_values={"ontology": ontology_text},
            event_indices=event_indices,
        )
        repaired_by_id = {str(coding["event_uid"]): coding for coding in repaired}
        codings = [
            repaired_by_id.get(str(coding["event_uid"]), coding) for coding in codings
        ]
    for coding in codings:
        for field, identifiers in allowed.items():
            value = coding.get(field)
            if value is not None and value not in identifiers:
                raise ValueError(
                    f"Closed coding used unknown {field} category {value!r} for "
                    f"{coding.get('event_uid')}"
                )
        coding["label_source"] = "llm_closed_coding"
        coding["ontology_name"] = ontology.get("name")
        coding["ontology_version"] = ontology.get("version")
    output_path = destination / "closed_codings.jsonl"
    write_jsonl(output_path, codings)
    return output_path


def iterative_code(
    events_path: Path | str,
    output_dir: Path | str,
    runner: StructuredRunner,
    *,
    batch_size: int = 20,
    discovery_rounds: int = 3,
    max_iterations: int = 8,
    stable_rounds: int = 2,
    random_seed: int = 1729,
    max_no_fit_rate: float = 0.01,
    max_ambiguous_rate: float = 0.01,
    max_change_rate: float = 0.01,
) -> Path:
    """Discover and freeze a v1 ontology, then validate it until coding stabilizes."""
    if discovery_rounds < 1:
        raise ValueError("discovery_rounds must be at least 1")
    if max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")
    if stable_rounds < 1:
        raise ValueError("stable_rounds must be at least 1")
    if not 0.0 <= max_no_fit_rate <= 1.0:
        raise ValueError("max_no_fit_rate must be between 0 and 1")
    if not 0.0 <= max_ambiguous_rate <= 1.0:
        raise ValueError("max_ambiguous_rate must be between 0 and 1")
    if not 0.0 <= max_change_rate <= 1.0:
        raise ValueError("max_change_rate must be between 0 and 1")

    source = Path(events_path)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    events = read_jsonl(source)
    LOGGER.info(
        "Iterative coding started: events=%s discovery_rounds=%s "
        "max_iterations=%s stable_rounds=%s frozen_ontology_version=1",
        len(events),
        discovery_rounds,
        max_iterations,
        stable_rounds,
    )
    if max_iterations < stable_rounds + 1:
        LOGGER.warning(
            "Saturation cannot be reached with max_iterations=%s and "
            "stable_rounds=%s because the first validation round is a baseline; "
            "use max_iterations=%s or higher",
            max_iterations,
            stable_rounds,
            stable_rounds + 1,
        )
    all_open_codings: list[dict[str, Any]] = []
    discovery_paths: list[Path] = []

    for round_index in range(1, discovery_rounds + 1):
        LOGGER.info(
            "Discovery round %s/%s started",
            round_index,
            discovery_rounds,
        )
        order = list(range(len(events)))
        random.Random(random_seed + round_index - 1).shuffle(order)
        round_dir = destination / "discovery" / f"round_{round_index:03d}"
        round_path = open_code(
            source,
            round_dir,
            runner,
            batch_size,
            event_indices=order,
        )
        round_codings = read_jsonl(round_path)
        for coding in round_codings:
            coding["discovery_round"] = round_index
        write_jsonl(round_path, round_codings)
        all_open_codings.extend(round_codings)
        discovery_paths.append(round_path)
        LOGGER.info(
            "Discovery round %s/%s completed: codings=%s output=%s",
            round_index,
            discovery_rounds,
            len(round_codings),
            round_path,
        )

    combined_path = destination / "discovery" / "open_codings.all.jsonl"
    write_jsonl(combined_path, all_open_codings)
    discovery_disagreements = _open_coding_disagreements(all_open_codings)
    current_ontology_path = destination / "ontology.v1.json"
    LOGGER.info(
        "Consolidating %s discovery codings: disagreements=%s",
        len(all_open_codings),
        len(discovery_disagreements),
    )
    consolidate(combined_path, current_ontology_path, runner)
    current_ontology = json.loads(current_ontology_path.read_text(encoding="utf-8"))
    current_ontology["version"] = 1
    _write_json(current_ontology_path, current_ontology)

    previous_codings: list[dict[str, Any]] | None = None
    stable_streak = 0
    iteration_records: list[dict[str, Any]] = []
    final_closed_path: Path | None = None
    saturated = False

    LOGGER.info("Ontology frozen: version=1 output=%s", current_ontology_path)
    for iteration in range(1, max_iterations + 1):
        LOGGER.info(
            "Validation round %s/%s started: ontology_version=1 coding=%s/%s",
            iteration,
            max_iterations,
            len(events),
            len(events),
        )
        iteration_dir = destination / "validation" / f"round_{iteration:03d}"
        closed_path = closed_code(
            source,
            current_ontology_path,
            iteration_dir,
            runner,
            batch_size,
        )
        closed_codings = read_jsonl(closed_path)
        final_closed_path = closed_path
        event_count = len(closed_codings)
        no_fit_count = sum(coding.get("fit") == "no_fit" for coding in closed_codings)
        ambiguous_count = sum(
            coding.get("fit") == "ambiguous" for coding in closed_codings
        )
        no_fit_rate = no_fit_count / event_count if event_count else 0.0
        ambiguous_rate = ambiguous_count / event_count if event_count else 0.0
        changed_events = _coding_differences(previous_codings, closed_codings)
        change_count = len(changed_events) if changed_events is not None else None
        change_rate = (
            change_count / event_count
            if change_count is not None and event_count
            else (0.0 if change_count == 0 else None)
        )
        ontology_changed = None if previous_codings is None else False
        stable = (
            previous_codings is not None
            and no_fit_rate <= max_no_fit_rate
            and ambiguous_rate <= max_ambiguous_rate
            and change_rate is not None
            and change_rate <= max_change_rate
        )
        stable_streak = stable_streak + 1 if stable else 0
        record: dict[str, Any] = {
            "round": iteration,
            "ontology_version": 1,
            "ontology_changed": ontology_changed,
            "new_category_count": None if previous_codings is None else 0,
            "removed_category_count": None if previous_codings is None else 0,
            "event_count": event_count,
            "no_fit_count": no_fit_count,
            "no_fit_rate": no_fit_rate,
            "ambiguous_count": ambiguous_count,
            "ambiguous_rate": ambiguous_rate,
            "coding_change_count": change_count,
            "coding_change_rate": change_rate,
            "coding_change_scope": (
                "baseline" if previous_codings is None else "same_ontology"
            ),
            "changed_events": changed_events,
            "stable": stable,
            "stable_streak": stable_streak,
            "closed_codings": str(closed_path.relative_to(destination)),
        }
        iteration_records.append(record)
        LOGGER.info(
            "Validation round %s/%s completed: no_fit=%s/%s (%.2f%%) "
            "ambiguous=%s/%s (%.2f%%) changed_events=%s rate=%s "
            "ontology_version=1 ontology_changed=%s stable=%s streak=%s/%s",
            iteration,
            max_iterations,
            no_fit_count,
            event_count,
            no_fit_rate * 100,
            ambiguous_count,
            event_count,
            ambiguous_rate * 100,
            change_count if change_count is not None else "baseline",
            f"{change_rate * 100:.2f}%" if change_rate is not None else "baseline",
            ontology_changed,
            stable,
            stable_streak,
            stable_rounds,
        )
        if stable_streak >= stable_rounds:
            saturated = True
            LOGGER.info("Saturation reached after validation round %s", iteration)
            break
        previous_codings = closed_codings

    final_ontology_path = destination / "ontology.final.json"
    shutil.copyfile(current_ontology_path, final_ontology_path)
    final_closed_output = destination / "closed_codings.final.jsonl"
    if final_closed_path is not None:
        shutil.copyfile(final_closed_path, final_closed_output)

    report = {
        "status": "saturated" if saturated else "max_iterations_reached",
        "parameters": {
            "batch_size": batch_size,
            "discovery_rounds": discovery_rounds,
            "max_iterations": max_iterations,
            "stable_rounds": stable_rounds,
            "random_seed": random_seed,
            "max_no_fit_rate": max_no_fit_rate,
            "max_ambiguous_rate": max_ambiguous_rate,
            "max_change_rate": max_change_rate,
            "ontology_frozen": True,
            "model": getattr(getattr(runner, "config", None), "model", None),
            "reasoning_effort": getattr(
                getattr(runner, "config", None), "reasoning_effort", None
            ),
            "reuse_checkpoints_across_reasoning": getattr(
                getattr(runner, "config", None),
                "reuse_checkpoints_across_reasoning",
                False,
            ),
        },
        "discovery_outputs": [
            str(path.relative_to(destination)) for path in discovery_paths
        ],
        "discovery_disagreement_event_count": len(discovery_disagreements),
        "discovery_disagreement_rate": (
            len(discovery_disagreements) / len(events) if events else 0.0
        ),
        "discovery_disagreements": discovery_disagreements,
        "iterations": iteration_records,
        "final_ontology": str(final_ontology_path.relative_to(destination)),
        "final_closed_codings": str(final_closed_output.relative_to(destination)),
    }
    report_path = destination / "saturation_report.json"
    _write_json(report_path, report)
    LOGGER.info(
        "Iterative coding finished: status=%s report=%s ontology=%s codings=%s",
        report["status"],
        report_path,
        final_ontology_path,
        final_closed_output,
    )
    return report_path
