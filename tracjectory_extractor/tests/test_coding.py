import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tracjectory_extractor.coding import (
    closed_code,
    consolidate,
    iterative_code,
    open_code,
)
from tracjectory_extractor.extractor import read_jsonl, write_jsonl


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run(self, prompt, schema_path):
        self.calls.append((prompt, schema_path.name))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        coding_properties = (
            schema["properties"]
            .get("codings", {})
            .get("items", {})
            .get("properties", {})
        )
        if "action_label" in coding_properties:
            event_ids = _current_event_ids(prompt)
            return {
                "codings": [
                    {
                        "event_uid": event_id,
                        "action_label": "read_file",
                        "object_label": "source_code",
                        "discourse_role": None,
                        "subject_label": None,
                        "summary": "Reads source code",
                        "evidence": "sed parser.c",
                        "confidence": "high",
                    }
                    for event_id in event_ids
                ]
            }
        if "action_categories" in schema["properties"]:
            return {
                "name": "test_ontology",
                "version": 1,
                "action_categories": [_category("READ")],
                "object_categories": [_category("SOURCE")],
                "message_roles": [_category("PLAN")],
                "message_subjects": [_category("SOURCE")],
            }
        event_ids = _current_event_ids(prompt)
        return {
            "codings": [
                {
                    "event_uid": event_id,
                    "action": "READ",
                    "object": "SOURCE",
                    "message_role": None,
                    "message_subject": None,
                    "fit": "exact",
                    "alternatives": [],
                    "rationale": "Matches ontology",
                    "confidence": "high",
                }
                for event_id in event_ids
            ]
        }


class OmittingRunner(FakeRunner):
    def run(self, prompt, schema_path):
        result = super().run(prompt, schema_path)
        if "action_label" in result.get("codings", [{}])[0] and len(self.calls) == 1:
            result["codings"] = result["codings"][:-1]
        return result


class InvalidClosedCategoryRunner(FakeRunner):
    def run(self, prompt, schema_path):
        result = super().run(prompt, schema_path)
        if "codings" not in result or not result["codings"]:
            return result
        coding = result["codings"][0]
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        action_schema = (
            schema["properties"]
            .get("codings", {})
            .get("items", {})
            .get("properties", {})
            .get("action", {})
        )
        if "action" in coding and "enum" not in action_schema:
            coding["action"] = "READ, WRITE"
        return result


def _category(identifier):
    return {
        "id": identifier,
        "definition": identifier.title(),
        "include": ["matching events"],
        "exclude": ["non-matching events"],
        "examples": ["example"],
    }


def _current_event_ids(prompt):
    decoder = json.JSONDecoder()
    events_marker = "Events:\n\n"
    start = prompt.index("[", prompt.index(events_marker) + len(events_marker))
    data, _ = decoder.raw_decode(prompt[start:])
    return [item["current"]["event_uid"] for item in data]


class IterativeRunner:
    def __init__(self):
        self.closed_round = 0
        self.closed_orders = []
        self.discovery_orders = []
        self.call_count = 0

    def run(self, prompt, schema_path):
        self.call_count += 1
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        coding_properties = (
            schema["properties"]
            .get("codings", {})
            .get("items", {})
            .get("properties", {})
        )
        if "action_label" in coding_properties:
            event_ids = _current_event_ids(prompt)
            self.discovery_orders.append(event_ids)
            action_label = (
                "inspect_file" if len(self.discovery_orders) % 2 == 1 else "read_file"
            )
            return {
                "codings": [
                    {
                        "event_uid": event_id,
                        "action_label": action_label,
                        "object_label": "source_code",
                        "discourse_role": None,
                        "subject_label": None,
                        "summary": "Inspects source code",
                        "evidence": "sed parser.c",
                        "confidence": "high",
                    }
                    for event_id in event_ids
                ]
            }
        if "action_categories" in schema["properties"]:
            return {
                "name": "iterative_test",
                "version": 99,
                "action_categories": [_category("READ")],
                "object_categories": [_category("SOURCE")],
                "message_roles": [_category("PLAN")],
                "message_subjects": [_category("SOURCE")],
            }

        self.closed_round += 1
        event_ids = _current_event_ids(prompt)
        self.closed_orders.append(event_ids)
        object_category = "SOURCE" if self.closed_round == 1 else None
        return {
            "codings": [
                {
                    "event_uid": event_id,
                    "action": "READ",
                    "object": object_category,
                    "message_role": None,
                    "message_subject": None,
                    "fit": "exact",
                    "alternatives": [],
                    "rationale": "Matches the frozen ontology",
                    "confidence": "high",
                }
                for event_id in event_ids
            ]
        }


class CodingTests(unittest.TestCase):
    def test_complete_coding_pipeline_and_batch_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events_path = root / "events.jsonl"
            events = [
                {
                    "event_uid": f"run:event-{index}",
                    "run_id": "run",
                    "event_type": "command",
                    "raw_item_type": "command_execution",
                    "command": f"sed -n '{index}p' parser.c",
                    "output": "source",
                    "exit_code": 0,
                    "text": None,
                    "changes": None,
                    "payload": {},
                }
                for index in range(3)
            ]
            write_jsonl(events_path, events)
            runner = FakeRunner()

            open_path = open_code(events_path, root, runner, batch_size=2)
            first_call_count = len(runner.calls)
            open_code(events_path, root, runner, batch_size=2)
            ontology_path = consolidate(open_path, root / "ontology.v1.json", runner)
            closed_path = closed_code(
                events_path, ontology_path, root, runner, batch_size=2
            )

            self.assertEqual(len(read_jsonl(open_path)), 3)
            closed_records = read_jsonl(closed_path)
            self.assertEqual(len(closed_records), 3)
            self.assertEqual(closed_records[0]["ontology_name"], "test_ontology")
            self.assertEqual(closed_records[0]["ontology_version"], 1)
            self.assertEqual(first_call_count, 2)
            self.assertEqual(len(runner.calls), 5)
            self.assertEqual(
                json.loads(ontology_path.read_text())["name"], "test_ontology"
            )
            self.assertNotIn("run_status", runner.calls[0][0])

    def test_incomplete_batch_retries_only_omitted_events_before_caching(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events_path = root / "events.jsonl"
            events = [
                {
                    "event_uid": f"run:event-{index}",
                    "run_id": "run",
                    "event_type": "command",
                    "raw_item_type": "command_execution",
                    "command": f"sed -n '{index}p' parser.c",
                    "output": "source",
                    "exit_code": 0,
                    "text": None,
                    "changes": None,
                    "payload": {},
                }
                for index in range(3)
            ]
            write_jsonl(events_path, events)
            runner = OmittingRunner()

            with self.assertLogs(
                "tracjectory_extractor.coding", level="INFO"
            ) as captured:
                output_path = open_code(events_path, root, runner, batch_size=3)
                open_code(events_path, root, runner, batch_size=3)

            self.assertEqual(len(runner.calls), 2)
            self.assertEqual(_current_event_ids(runner.calls[1][0]), ["run:event-2"])
            self.assertIn("REPAIR REQUEST", runner.calls[1][0])
            self.assertIn("Return exactly 1 coding record", runner.calls[1][0])
            self.assertEqual(len(read_jsonl(output_path)), 3)
            checkpoint = json.loads(
                (root / "open_coding_batches" / "batch_00000.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(len(checkpoint["response"]["codings"]), 3)
            repair_schema = json.loads(
                (
                    root / "open_coding_batches" / "batch_00000.repair.schema.json"
                ).read_text(encoding="utf-8")
            )
            repair_codings = repair_schema["properties"]["codings"]
            self.assertEqual(repair_codings["minItems"], 1)
            self.assertEqual(repair_codings["maxItems"], 1)
            self.assertEqual(
                repair_codings["items"]["properties"]["event_uid"]["enum"],
                ["run:event-2"],
            )
            logs = "\n".join(captured.output)
            self.assertIn("repair attempt 1/3 for 1 events", logs)
            self.assertIn("checkpoint hit", logs)

    def test_closed_coding_repairs_unknown_category_without_rerunning_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events_path = root / "events.jsonl"
            write_jsonl(
                events_path,
                [
                    {
                        "event_uid": "run:event-0",
                        "run_id": "run",
                        "event_type": "command",
                        "raw_item_type": "command_execution",
                        "command": "sed -n '1p' parser.c",
                        "output": "source",
                        "exit_code": 0,
                        "text": None,
                        "changes": None,
                        "payload": {},
                    }
                ],
            )
            ontology_path = root / "ontology.json"
            ontology_path.write_text(
                json.dumps(
                    {
                        "name": "test_ontology",
                        "version": 1,
                        "action_categories": [_category("READ")],
                        "object_categories": [_category("SOURCE")],
                        "message_roles": [_category("PLAN")],
                        "message_subjects": [_category("SOURCE")],
                    }
                ),
                encoding="utf-8",
            )
            runner = InvalidClosedCategoryRunner()

            with self.assertLogs(
                "tracjectory_extractor.coding", level="INFO"
            ) as captured:
                output_path = closed_code(
                    events_path, ontology_path, root / "closed", runner
                )
                closed_code(events_path, ontology_path, root / "closed", runner)

            rows = read_jsonl(output_path)
            self.assertEqual(rows[0]["action"], "READ")
            self.assertEqual(len(runner.calls), 2)
            logs = "\n".join(captured.output)
            self.assertIn("recoding only those events", logs)
            self.assertIn("checkpoint hit", logs)

    def test_batch_cache_is_invalidated_when_model_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events_path = root / "events.jsonl"
            write_jsonl(
                events_path,
                [
                    {
                        "event_uid": "run:event-0",
                        "run_id": "run",
                        "event_type": "command",
                        "raw_item_type": "command_execution",
                        "command": "sed -n '1p' parser.c",
                        "output": "source",
                        "exit_code": 0,
                        "text": None,
                        "changes": None,
                        "payload": {},
                    }
                ],
            )
            first_runner = FakeRunner()
            first_runner.config = SimpleNamespace(
                executable="codex",
                model="gpt-5.6-luna",
                reasoning_effort="xhigh",
            )
            second_runner = FakeRunner()
            second_runner.config = SimpleNamespace(
                executable="codex",
                model="gpt-5.6-sol",
                reasoning_effort="xhigh",
            )

            with self.assertLogs(
                "tracjectory_extractor.coding", level="INFO"
            ) as captured:
                open_code(events_path, root, first_runner)
                open_code(events_path, root, first_runner)
                open_code(events_path, root, second_runner)

            self.assertEqual(len(first_runner.calls), 1)
            self.assertEqual(len(second_runner.calls), 1)
            logs = "\n".join(captured.output)
            self.assertIn("Batch 1/1: requesting Codex coding", logs)
            self.assertIn("Batch 1/1: checkpoint hit", logs)
            self.assertIn("Batch 1/1: complete", logs)

    def test_batch_cache_can_be_reused_when_only_reasoning_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events_path = root / "events.jsonl"
            write_jsonl(
                events_path,
                [
                    {
                        "event_uid": "run:event-0",
                        "run_id": "run",
                        "event_type": "command",
                        "raw_item_type": "command_execution",
                        "command": "sed -n '1p' parser.c",
                        "output": "source",
                        "exit_code": 0,
                        "text": None,
                        "changes": None,
                        "payload": {},
                    }
                ],
            )
            first_runner = FakeRunner()
            first_runner.config = SimpleNamespace(
                executable="codex",
                model="gpt-5.6-luna",
                reasoning_effort="max",
                reuse_checkpoints_across_reasoning=False,
            )
            second_runner = FakeRunner()
            second_runner.config = SimpleNamespace(
                executable="codex",
                model="gpt-5.6-luna",
                reasoning_effort="xhigh",
                reuse_checkpoints_across_reasoning=True,
            )

            open_code(events_path, root, first_runner)
            with self.assertLogs(
                "tracjectory_extractor.coding", level="INFO"
            ) as captured:
                open_code(events_path, root, second_runner)

            self.assertEqual(len(first_runner.calls), 1)
            self.assertEqual(len(second_runner.calls), 0)
            self.assertIn("reused across reasoning effort", "\n".join(captured.output))

    def test_iterative_coding_freezes_v1_and_reports_changed_events(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events_path = root / "events.jsonl"
            events = [
                {
                    "event_uid": f"run:event-{index}",
                    "run_id": "run",
                    "event_type": "command",
                    "raw_item_type": "command_execution",
                    "command": f"sed -n '{index}p' parser.c",
                    "output": "source",
                    "exit_code": 0,
                    "text": None,
                    "changes": None,
                    "payload": {},
                }
                for index in range(5)
            ]
            write_jsonl(events_path, events)
            runner = IterativeRunner()

            report_path = iterative_code(
                events_path,
                root / "iterative",
                runner,
                batch_size=10,
                discovery_rounds=2,
                max_iterations=5,
                stable_rounds=2,
                random_seed=23,
            )

            report = json.loads(report_path.read_text(encoding="utf-8"))
            final_ontology = json.loads(
                (root / "iterative" / "ontology.final.json").read_text(encoding="utf-8")
            )
            final_codings = read_jsonl(
                root / "iterative" / "closed_codings.final.jsonl"
            )

            self.assertEqual(report["status"], "saturated")
            self.assertEqual(report["discovery_disagreement_event_count"], 5)
            self.assertEqual(report["discovery_disagreement_rate"], 1.0)
            self.assertEqual(len(report["iterations"]), 4)
            self.assertEqual(report["iterations"][-1]["stable_streak"], 2)
            self.assertEqual(len(report["iterations"][1]["changed_events"]), 5)
            self.assertEqual(
                report["iterations"][1]["changed_events"][0]["changed_fields"],
                ["object"],
            )
            self.assertEqual(final_ontology["version"], 1)
            self.assertEqual(
                {category["id"] for category in final_ontology["action_categories"]},
                {"READ"},
            )
            self.assertTrue(all(coding["fit"] == "exact" for coding in final_codings))
            self.assertNotEqual(runner.discovery_orders[0], runner.discovery_orders[1])
            self.assertEqual([len(order) for order in runner.closed_orders], [5] * 4)

            call_count = runner.call_count
            iterative_code(
                events_path,
                root / "iterative",
                runner,
                batch_size=10,
                discovery_rounds=2,
                max_iterations=5,
                stable_rounds=2,
                random_seed=23,
            )
            self.assertEqual(runner.call_count, call_count)

    def test_iterative_coding_rejects_invalid_ambiguous_rate(self):
        with self.assertRaisesRegex(ValueError, "max_ambiguous_rate"):
            iterative_code(
                "unused.jsonl",
                "unused",
                FakeRunner(),
                max_ambiguous_rate=1.1,
            )

    def test_iterative_coding_codes_all_events_in_every_validation_round(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events_path = root / "events.jsonl"
            write_jsonl(
                events_path,
                [
                    {
                        "event_uid": f"run:event-{index}",
                        "run_id": "run",
                        "event_type": "command",
                        "raw_item_type": "command_execution",
                        "command": f"sed -n '{index}p' parser.c",
                        "output": "source",
                        "exit_code": 0,
                        "text": None,
                        "changes": None,
                        "payload": {},
                    }
                    for index in range(10)
                ],
            )
            runner = FakeRunner()

            report_path = iterative_code(
                events_path,
                root / "iterative",
                runner,
                batch_size=20,
                discovery_rounds=1,
                max_iterations=4,
                stable_rounds=2,
            )

            report = json.loads(report_path.read_text(encoding="utf-8"))
            closed_call_sizes = [
                len(_current_event_ids(prompt))
                for prompt, schema_name in runner.calls
                if schema_name == "closed_coding.schema.json"
            ]
            self.assertEqual(closed_call_sizes, [10, 10, 10])
            self.assertEqual(report["iterations"][-1]["changed_events"], [])
            self.assertTrue(report["parameters"]["ontology_frozen"])


if __name__ == "__main__":
    unittest.main()
