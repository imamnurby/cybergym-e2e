import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from trajectory_report import build_report_data, discover_logs, main, render_html


SAMPLE_RUN = {
    "source": "/tmp/example_run.log",
    "task": "example/arvo_1",
    "agent": "openhands",
    "model": "openai/test-model",
    "prompt_style": "iterative",
    "status": "failed",
    "duration_seconds": 120,
    "timeout_seconds": 120,
    "exit_code": 124,
    "events": [
        {
            "timestamp": "10:00:01",
            "offset_seconds": 1,
            "kind": "action",
            "action_type": "CmdRunAction",
            "title": "Inspect source",
            "detail": "rg vulnerable_function",
            "phase": "investigation",
            "line": 12,
        }
    ],
    "steps": [
        {
            "phase": "investigation",
            "title": "Inspect source",
            "start_seconds": 1,
            "end_seconds": 119,
            "duration_seconds": 118,
            "event_count": 1,
            "summary": "The agent inspected the target.",
            "evidence_lines": ["L12: rg vulnerable_function"],
        }
    ],
    "idle_gaps": [
        {
            "start_seconds": 2,
            "end_seconds": 90,
            "duration_seconds": 88,
            "start_timestamp": "10:00:02",
            "end_timestamp": "10:01:30",
        }
    ],
    "markers": [
        {
            "kind": "timeout",
            "title": "Agent timed out",
            "detail": "exit=124",
            "timestamp": "10:02:00",
            "line": 30,
        }
    ],
    "validation": [],
    "artifacts": {"poc": False, "patch": False},
}


class DiscoverLogsTests(unittest.TestCase):
    def test_discovers_nested_run_logs_and_deduplicates_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nested = root / "nested"
            nested.mkdir()
            first = root / "a_run.log"
            second = nested / "b_run.log"
            ignored = nested / "other.log"
            first.write_text("a", encoding="utf-8")
            second.write_text("b", encoding="utf-8")
            ignored.write_text("ignored", encoding="utf-8")

            result = discover_logs([root, first])

        self.assertEqual(result, sorted([first.resolve(), second.resolve()]))

    def test_rejects_missing_input(self):
        with self.assertRaisesRegex(FileNotFoundError, "Input does not exist"):
            discover_logs([Path("/definitely/missing/trajectory-input")])


class RenderHtmlTests(unittest.TestCase):
    def test_build_report_data_keeps_each_appended_session(self):
        first = {**SAMPLE_RUN, "model": "claude-opus-4-6"}
        second = {**SAMPLE_RUN, "model": "claude-opus-4-5"}

        with patch(
            "trajectory_report.parse_trajectories", return_value=[first, second]
        ):
            runs = build_report_data([Path("example_run.log")])

        self.assertEqual(
            [run["model"] for run in runs],
            ["claude-opus-4-6", "claude-opus-4-5"],
        )

    def test_report_is_portable_and_contains_expected_controls(self):
        html = render_html(
            [SAMPLE_RUN],
            title="Test trajectories",
            generated_at="2026-08-06T00:00:00+00:00",
        )

        self.assertIn("<!doctype html>", html)
        self.assertIn("Test trajectories", html)
        self.assertIn('id="status-filter"', html)
        self.assertIn('id="comparison-body"', html)
        self.assertIn("Hatched areas show idle gaps", html)
        self.assertIn("Detailed actions", html)
        self.assertIn("Show full detail", html)
        self.assertIn('const pageSize = 250;', html)
        self.assertIn('selectControl("Phases", phases)', html)
        self.assertIn('selectControl("Kinds", kinds)', html)
        self.assertIn("event.action_type", html)
        self.assertIn('`L${event.line}`', html)
        self.assertIn('return lines.join("\\n");', html)
        self.assertNotIn('<script src="', html)
        self.assertNotIn('<link rel="stylesheet"', html)

        encoded = html.split(
            '<script id="report-data" type="application/json">', 1
        )[1].split("</script>", 1)[0]
        payload = json.loads(encoded)
        self.assertEqual(payload["runs"][0]["task"], "example/arvo_1")

    def test_embedded_json_cannot_close_its_script_element(self):
        run = {**SAMPLE_RUN, "task": "</script><script>alert(1)</script>"}

        html = render_html(
            [run], generated_at="2026-08-06T00:00:00+00:00"
        )
        encoded = html.split(
            '<script id="report-data" type="application/json">', 1
        )[1].split("</script>", 1)[0]

        self.assertNotIn("</script>", encoded)
        self.assertIn("\\u003c/script\\u003e", encoded)

    def test_main_writes_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "example_run.log"
            output = root / "report.html"
            log.write_text("Task: example/arvo_1\n", encoding="utf-8")

            with patch(
                "trajectory_report.build_report_data", return_value=[SAMPLE_RUN]
            ):
                result = main([str(log), "--output", str(output), "--title", "Test"])

            html = output.read_text(encoding="utf-8")

        self.assertEqual(result, 0)
        self.assertIn("Test", html)


if __name__ == "__main__":
    unittest.main()
