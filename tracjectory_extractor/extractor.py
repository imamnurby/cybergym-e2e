"""Normalize Codex JSONL trajectories without assigning semantic labels."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1


def discover_trajectories(inputs: Iterable[Path | str]) -> list[Path]:
    """Discover unique Codex trajectory JSONL files in deterministic order."""
    found: set[Path] = set()
    for value in inputs:
        path = Path(value).expanduser()
        if path.is_file():
            if path.suffix != ".jsonl":
                raise ValueError(f"Expected a JSONL trajectory: {path}")
            found.add(path.resolve())
        elif path.is_dir():
            found.update(
                candidate.resolve()
                for candidate in path.rglob("trajectory/attempt_*.jsonl")
            )
        else:
            raise FileNotFoundError(f"Input does not exist: {path}")
    return sorted(found, key=str)


def _read_summary(source: Path) -> dict[str, Any]:
    summary_path = source.parent.parent / "summary.json"
    if not summary_path.is_file():
        return {}
    try:
        value = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _metadata(record: dict[str, Any]) -> tuple[float | None, str | None]:
    metadata = record.get("_cybergym")
    if not isinstance(metadata, dict):
        return None, None
    elapsed = metadata.get("elapsed_seconds")
    captured_at = metadata.get("captured_at")
    return (
        float(elapsed) if isinstance(elapsed, (int, float)) else None,
        captured_at if isinstance(captured_at, str) else None,
    )


def _event_type(item_type: str) -> str:
    return {
        "agent_message": "message",
        "reasoning": "message",
        "command_execution": "command",
        "file_change": "file_change",
        "error": "error",
    }.get(item_type, "other")


def _run_id(source: Path, summary: dict[str, Any]) -> str:
    task = str(summary.get("task") or source.parent.parent.parent.name)
    run = source.parent.parent.name
    return f"{task.replace('/', '_')}:{run}:{source.stem}"


def _normalized_event(
    *,
    source: Path,
    summary: dict[str, Any],
    item: dict[str, Any],
    item_id: str,
    started: tuple[int, dict[str, Any]] | None,
    completed: tuple[int, dict[str, Any]] | None,
) -> dict[str, Any]:
    started_line, started_record = started or (None, {})
    completed_line, completed_record = completed or (None, {})
    start_seconds, start_timestamp = _metadata(started_record)
    end_seconds, end_timestamp = _metadata(completed_record)
    if started is None:
        start_seconds, start_timestamp = end_seconds, end_timestamp
    if completed is None:
        end_seconds, end_timestamp = start_seconds, start_timestamp

    item_type = str(item.get("type") or "unknown")
    event: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": _run_id(source, summary),
        "event_id": item_id,
        "event_uid": f"{_run_id(source, summary)}:{item_id}",
        "event_index": -1,
        "event_type": _event_type(item_type),
        "raw_item_type": item_type,
        "started_seconds": start_seconds,
        "completed_seconds": end_seconds,
        "duration_seconds": (
            max(0.0, end_seconds - start_seconds)
            if start_seconds is not None and end_seconds is not None
            else None
        ),
        "started_at": start_timestamp,
        "completed_at": end_timestamp,
        "status": item.get("status"),
        "exit_code": item.get("exit_code"),
        "command": item.get("command"),
        "output": item.get("aggregated_output"),
        "text": item.get("text"),
        "changes": item.get("changes"),
        "payload": item,
        "source": str(source),
        "source_lines": [
            line for line in (started_line, completed_line) if line is not None
        ],
        "task": summary.get("task"),
        "agent": summary.get("agent"),
        "model": summary.get("model"),
        "prompt_style": summary.get("prompt_style"),
        "run_status": summary.get("status"),
    }
    return event


def normalize_trajectory(path: Path | str) -> list[dict[str, Any]]:
    """Return one normalized event per logical Codex item.

    ``item.started`` and ``item.completed`` records are correlated by item ID.
    Completed-only messages and file changes remain single logical events.
    """
    source = Path(path).expanduser().resolve()
    summary = _read_summary(source)
    started: dict[str, tuple[int, dict[str, Any]]] = {}
    completed: dict[str, tuple[int, dict[str, Any]]] = {}
    updates: list[tuple[str, int, dict[str, Any]]] = []
    completion_order: list[str] = []
    synthetic = 0

    with source.open(encoding="utf-8", errors="replace") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            event_type = record.get("type")
            item = record.get("item")
            if event_type not in {
                "item.started",
                "item.updated",
                "item.completed",
            } or not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "")
            if not item_id:
                synthetic += 1
                item_id = f"line-{line_number}-{synthetic}"
            if event_type == "item.started":
                started[item_id] = (line_number, record)
            elif event_type == "item.completed":
                completed[item_id] = (line_number, record)
                if item_id not in completion_order:
                    completion_order.append(item_id)
            else:
                updates.append((item_id, line_number, record))

    for item_id in started:
        if item_id not in completed:
            completion_order.append(item_id)

    events: list[dict[str, Any]] = []
    for item_id in completion_order:
        start = started.get(item_id)
        end = completed.get(item_id)
        record = (end or start)[1]
        item = record["item"]
        events.append(
            _normalized_event(
                source=source,
                summary=summary,
                item=item,
                item_id=item_id,
                started=start,
                completed=end,
            )
        )

    for item_id, line_number, record in updates:
        update_id = f"{item_id}-update-L{line_number}"
        events.append(
            _normalized_event(
                source=source,
                summary=summary,
                item=record["item"],
                item_id=update_id,
                started=None,
                completed=(line_number, record),
            )
        )

    events.sort(
        key=lambda event: (
            event["started_seconds"] is None,
            event["started_seconds"] if event["started_seconds"] is not None else 0,
            event["source_lines"][0] if event["source_lines"] else 0,
        )
    )
    for index, event in enumerate(events):
        event["event_index"] = index
    return events


def write_jsonl(path: Path | str, records: Iterable[dict[str, Any]]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected object at {path}:{line_number}")
            records.append(value)
    return records
