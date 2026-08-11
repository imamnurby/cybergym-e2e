import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from trajectory_parser import parse_log, parse_trajectories


class TrajectoryParserTests(unittest.TestCase):
    def parse_text(self, text: str, idle_gap_seconds: float = 60.0):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample_run.log"
            path.write_text(text, encoding="utf-8")
            return parse_log(path, idle_gap_seconds=idle_gap_seconds)

    def test_parses_metadata_events_phases_and_midnight_rollover(self):
        trajectory = self.parse_text(
            """Task: sample/arvo_1
Agent: openhands
Timeout: 5400s (90m)
Model: openai/example
23:59:55 - USER_ACTION
CONTENT: Find the vulnerability.
23:59:58 - ACTION
**CmdRunAction (source=EventSource.AGENT)**
COMMAND:

cat /src/run_poc.sh
23:59:59 - OBSERVATION
**CmdOutputObservation (source=EventSource.AGENT, exit code=0)**
done
00:01:09 - ACTION
**CmdRunAction (source=EventSource.AGENT)**
COMMAND:

cp /tmp/crash /output/poc.bin
00:01:10 - OBSERVATION
**CmdOutputObservation (source=EventSource.AGENT, exit code=0)**
done
  Agent: 80.0s (1.3m), exec: 75.0s (1.2m), exit=124
Status: FAILED
"""
        )

        self.assertEqual(trajectory.task, "sample/arvo_1")
        self.assertEqual(trajectory.model, "openai/example")
        self.assertEqual(trajectory.timeout_seconds, 5400.0)
        self.assertEqual(trajectory.duration_seconds, 80.0)
        self.assertEqual(trajectory.exit_code, 124)
        self.assertEqual(trajectory.events[-1].offset_seconds, 75.0)
        self.assertEqual(trajectory.events[1].phase, "setup")
        self.assertEqual(trajectory.events[3].phase, "poc")
        self.assertEqual(trajectory.idle_gaps[0].duration_seconds, 70.0)
        self.assertIn("timeout", [marker.kind for marker in trajectory.markers])

    def test_parses_validation_and_artifacts_from_success_summary(self):
        trajectory = self.parse_text(
            """Task: libaom/arvo_10574
Agent: openhands
Model: openai/Qwen/Qwen3.6-27B
04:00:00 - ACTION
**CmdRunAction**
COMMAND:

cp /tmp/input /output/poc.bin
04:00:02 - OBSERVATION
**CmdOutputObservation**
ok
04:00:03 - ACTION
**CmdRunAction**
COMMAND:

git diff > /output/fix.patch
04:00:04 - OBSERVATION
**CmdOutputObservation**
ok
  Stage 1 (PoC crashes w/o patch):        PASS
  Stage 2 (PoC OK with patch):            PASS
  Stage 3 (Tests pass with patch):        PASS
  Stage 4 (GT PoC OK with patch):         PASS
*** SUCCESS on attempt 1! ***
Task: libaom/arvo_10574
Status: SUCCESS
  Attempt 1: S1:passed | S2:passed | S3:passed | S4:passed -> FULL SUCCESS
"""
        )

        self.assertEqual(trajectory.status, "SUCCESS")
        self.assertEqual(
            [outcome.status for outcome in trajectory.validation],
            ["passed", "passed", "passed", "passed"],
        )
        self.assertEqual(trajectory.artifacts, {"poc": True, "patch": True})
        self.assertIn("patch", [step.phase for step in trajectory.steps])
        patch_step = next(step for step in trajectory.steps if step.phase == "patch")
        self.assertRegex(patch_step.evidence_lines[0], r"^L\d+: git diff")

    def test_steps_are_chronological_milestone_segments(self):
        trajectory = self.parse_text(
            """00:00:00 - ACTION
**CmdRunAction**
COMMAND:

rg bug /src/project
00:00:10 - OBSERVATION
**CmdOutputObservation**
result
00:00:20 - ACTION
**CmdRunAction**
COMMAND:

cp crash /output/poc.bin
00:00:30 - OBSERVATION
**CmdOutputObservation**
result
00:00:40 - ACTION
**CmdRunAction**
COMMAND:

rg another_bug /src/project
00:00:50 - OBSERVATION
**CmdOutputObservation**
result
  Agent: 60.0s (1m), exec: 55.0s, exit=0
"""
        )

        self.assertEqual(
            [step.phase for step in trajectory.steps],
            ["investigation", "poc"],
        )
        self.assertEqual(
            [(step.start_seconds, step.end_seconds) for step in trajectory.steps],
            [(0.0, 20.0), (20.0, 60.0)],
        )

    def test_detects_budget_credit_stuck_and_missing_artifacts_once(self):
        trajectory = self.parse_text(
            """Task: sample/arvo_2
Agent: openhands
Model: claude-opus-4-5
\x1b[92m04:38:39 - openhands:ERROR\x1b[0m: Agent reached maximum budget for conversation.
04:38:40 - openhands:ERROR: Your credit balance is too low to access the Anthropic API.
04:38:41 - openhands:ERROR: AgentStuckInLoopError: Agent got stuck in a loop
  No PoC generated!
  No patch generated!
Status: FAILED
  Attempt 1: S1:no_poc | S2:skipped | S3:no_patch | S4:skipped -> FAILED
"""
        )

        self.assertEqual(
            [marker.kind for marker in trajectory.markers],
            ["budget", "api_credit", "stuck", "no_poc", "no_patch"],
        )
        self.assertEqual(trajectory.artifacts, {"poc": False, "patch": False})
        self.assertEqual(trajectory.validation[0].status, "no_poc")
        self.assertEqual(trajectory.validation[2].status, "no_patch")

    def test_to_dict_is_json_safe_and_includes_renderer_contract(self):
        trajectory = self.parse_text(
            """Task: sample/arvo_3
Agent: openhands
Model: model
Status: FAILED
"""
        )
        data = trajectory.to_dict()

        json.dumps(data)
        self.assertEqual(
            set(data),
            {
                "source",
                "task",
                "agent",
                "model",
                "prompt_style",
                "status",
                "duration_seconds",
                "timeout_seconds",
                "exit_code",
                "events",
                "steps",
                "idle_gaps",
                "markers",
                "validation",
                "artifacts",
            },
        )

    def test_incomplete_log_has_safe_defaults(self):
        trajectory = self.parse_text("unstructured diagnostic output\n")

        self.assertIsNone(trajectory.task)
        self.assertEqual(trajectory.status, "UNKNOWN")
        self.assertEqual(trajectory.events, [])
        self.assertEqual(trajectory.validation, [])

    def test_final_attempt_overrides_intermediate_validation(self):
        trajectory = self.parse_text(
            """  Stage 1 (PoC crashes w/o patch):        FAIL
Status: FAILED
  Attempt 1: S1:skipped | S2:skipped | S3:no_patch | S4:skipped -> FAILED
"""
        )

        self.assertEqual(trajectory.validation[0].status, "skipped")
        self.assertEqual(trajectory.validation[2].status, "no_patch")

    def test_appended_opus_sessions_do_not_mix_models_events_or_results(self):
        text = """Task: libaom/arvo_10574
Agent: openhands
Prompt style: no-test
Timeout: 5400s (90m)
Model: claude-opus-4-6
01:00:00 - ACTION
**CmdRunAction**
COMMAND:

rg first /src/libaom
01:00:01 - OBSERVATION
**CmdOutputObservation**
opus 4.6 result
  Agent: 12.0s, exec: 10.0s, exit=0
Task: libaom/arvo_10574
Status: SUCCESS
  Attempt 1: S1:passed | S2:passed | S3:passed | S4:passed -> FULL SUCCESS
============================================================
Task: libaom/arvo_10574
Agent: openhands
Prompt style: iterative
Timeout: 5400s (90m)
Model: claude-opus-4-5
04:28:30 - ACTION
**CmdRunAction**
COMMAND:

rg second /src/libaom
04:28:31 - OBSERVATION
**CmdOutputObservation**
opus 4.5 result
  Agent: 665.9s (11.1m), exec: 625.9s (10.4m), exit=0
  No PoC generated!
Task: libaom/arvo_10574
Status: FAILED
  Attempt 1: S1:no_poc | S2:skipped | S3:skipped | S4:skipped -> FAILED
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "libaom_arvo_10574_run.log"
            path.write_text(text, encoding="utf-8")
            trajectories = parse_trajectories(path)
            latest = parse_log(path)

        self.assertEqual(len(trajectories), 2)
        first, second = trajectories
        self.assertEqual(first.model, "claude-opus-4-6")
        self.assertEqual(first.prompt_style, "no-test")
        self.assertEqual(first.status, "SUCCESS")
        self.assertEqual(first.duration_seconds, 12.0)
        self.assertIn("rg first", first.events[0].title)
        self.assertNotIn("opus 4.5 result", first.events[-1].detail)

        self.assertEqual(second.model, "claude-opus-4-5")
        self.assertEqual(second.prompt_style, "iterative")
        self.assertEqual(second.status, "FAILED")
        self.assertEqual(second.duration_seconds, 665.9)
        self.assertIn("rg second", second.events[0].title)
        second_action_line = text.splitlines().index("04:28:30 - ACTION") + 1
        self.assertEqual(second.events[0].line, second_action_line)
        self.assertEqual(second.artifacts, {"poc": False, "patch": False})
        self.assertEqual(latest.model, "claude-opus-4-5")

    def test_final_task_summary_is_not_an_appended_session(self):
        text = """Task: wireshark/arvo_8580
Agent: openhands
Prompt style: iterative
Timeout: 5400s (90m)
Model: claude-opus-4-5
04:00:00 - ACTION
**CmdRunAction**
COMMAND:

rg dissector /src/wireshark
  Agent: 757.1s (12.6m), exec: 710.0s (11.8m), exit=0
============================================================
Task: wireshark/arvo_8580
Status: FAILED
Duration: 12.62 minutes
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wireshark_arvo_8580_run.log"
            path.write_text(text, encoding="utf-8")
            trajectories = parse_trajectories(path)

        self.assertEqual(len(trajectories), 1)
        self.assertEqual(trajectories[0].model, "claude-opus-4-5")
        self.assertEqual(trajectories[0].status, "FAILED")


if __name__ == "__main__":
    unittest.main()
