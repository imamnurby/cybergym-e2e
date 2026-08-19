import json
import tempfile
import unittest
from pathlib import Path

from tracjectory_extractor.extractor import discover_trajectories, normalize_trajectory


class ExtractorTests(unittest.TestCase):
    def test_correlates_items_and_loads_summary_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "project_arvo_1" / "run"
            trajectory_dir = run_dir / "trajectory"
            trajectory_dir.mkdir(parents=True)
            source = trajectory_dir / "attempt_1.jsonl"
            records = [
                {
                    "type": "item.started",
                    "item": {
                        "id": "cmd-1",
                        "type": "command_execution",
                        "command": "rg bug /src/project",
                        "status": "in_progress",
                    },
                    "_cybergym": {"elapsed_seconds": 2.0},
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "cmd-1",
                        "type": "command_execution",
                        "command": "rg bug /src/project",
                        "aggregated_output": "match",
                        "exit_code": 0,
                        "status": "completed",
                    },
                    "_cybergym": {"elapsed_seconds": 5.5},
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "message-1",
                        "type": "agent_message",
                        "text": "I found the candidate.",
                    },
                    "_cybergym": {"elapsed_seconds": 6.0},
                },
            ]
            source.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            (run_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "task": "project/arvo_1",
                        "agent": "codex",
                        "model": "luna",
                        "status": "success",
                    }
                ),
                encoding="utf-8",
            )

            events = normalize_trajectory(source)

        self.assertEqual(len(events), 2)
        command, message = events
        self.assertEqual(command["event_type"], "command")
        self.assertEqual(command["duration_seconds"], 3.5)
        self.assertEqual(command["source_lines"], [1, 2])
        self.assertEqual(command["output"], "match")
        self.assertEqual(command["task"], "project/arvo_1")
        self.assertEqual(message["event_type"], "message")
        self.assertEqual(message["text"], "I found the candidate.")
        self.assertNotEqual(command["event_uid"], message["event_uid"])

    def test_preserves_item_updates_and_incomplete_started_items(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "attempt_1.jsonl"
            records = [
                {
                    "type": "item.started",
                    "item": {
                        "id": "cmd-1",
                        "type": "command_execution",
                        "command": "sleep 1",
                    },
                    "_cybergym": {"elapsed_seconds": 1.0},
                },
                {
                    "type": "item.updated",
                    "item": {
                        "id": "todo-1",
                        "type": "todo_list",
                        "items": [{"text": "Inspect", "completed": True}],
                    },
                    "_cybergym": {"elapsed_seconds": 2.0},
                },
            ]
            source.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )

            events = normalize_trajectory(source)

        self.assertEqual(
            [event["event_type"] for event in events], ["command", "other"]
        )
        self.assertEqual(events[0]["source_lines"], [1])
        self.assertIn("update-L2", events[1]["event_id"])

    def test_discovers_trajectory_files_in_deterministic_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            second = root / "b" / "run" / "trajectory" / "attempt_2.jsonl"
            first = root / "a" / "run" / "trajectory" / "attempt_1.jsonl"
            second.parent.mkdir(parents=True)
            first.parent.mkdir(parents=True)
            second.write_text("")
            first.write_text("")

            paths = discover_trajectories([root])

        self.assertEqual(
            [path.name for path in paths], ["attempt_1.jsonl", "attempt_2.jsonl"]
        )


if __name__ == "__main__":
    unittest.main()
