from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import run_agent


def _codex_args(auth_file: Path, **overrides) -> SimpleNamespace:
    values = dict(
        model_provider="openai",
        litellm_model_id="openai/gpt-5.2-codex",
        openai_model_id="gpt-5.4",
        deepseek_model_id="deepseek-v4-pro",
        bedrock_model_id="bedrock-model",
        anthropic_model_id="anthropic-model",
        aws_region="us-west-2",
        aws_profile=None,
        max_budget_per_task=0,
        codex_auth_mode="chatgpt",
        codex_auth_file=str(auth_file),
        codex_reasoning_effort="",
        codex_supports_reasoning_summaries="auto",
        timeout=30,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class CodexSubscriptionAuthTests(unittest.TestCase):
    def test_qwen_api_configuration_sets_responses_and_reasoning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "trajectory.jsonl"
            exec_calls = []

            def fake_exec(container_id, command, description=None, **kwargs):
                exec_calls.append((command, description, kwargs))
                return 0, "", ""

            qwen_env = {
                "OPENAI_API_KEY": "EMPTY",
                "OPENAI_BASE_URL": "http://172.17.0.1:8100/v1",
            }
            args = _codex_args(
                Path(temp_dir) / "unused-auth.json",
                openai_model_id="Qwen/Qwen3.6-27B",
                codex_auth_mode="api-key",
                codex_reasoning_effort="medium",
                codex_supports_reasoning_summaries="false",
            )

            with (
                patch.object(
                    run_agent,
                    "get_llm_env",
                    return_value=(qwen_env, "openai/Qwen/Qwen3.6-27B"),
                ),
                patch.object(run_agent, "exec_run", side_effect=fake_exec),
                patch.object(
                    run_agent, "_stream_codex_exec", return_value=0
                ) as stream_exec,
            ):
                result = run_agent._execute_codex(
                    "container-id",
                    "find and fix the bug",
                    output_file,
                    args,
                )

            self.assertEqual(result, 0)
            all_commands = "\n".join(call[0] for call in exec_calls)
            self.assertIn('model_reasoning_effort = "medium"', all_commands)
            self.assertIn(
                "model_supports_reasoning_summaries = false", all_commands
            )
            self.assertIn('wire_api = "responses"', all_commands)
            self.assertIn(
                "--model Qwen/Qwen3.6-27B", stream_exec.call_args.args[1]
            )

    def test_subscription_auth_does_not_pass_api_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            auth_file = Path(temp_dir) / "auth.json"
            auth_file.write_text('{"tokens":{"access_token":"test"}}')
            output_file = Path(temp_dir) / "trajectory.jsonl"
            exec_calls = []

            def fake_exec(container_id, command, description=None, **kwargs):
                exec_calls.append((command, description, kwargs))
                return 0, '{"type":"done"}', ""

            with (
                patch.object(
                    run_agent,
                    "get_llm_env",
                    return_value=(
                        {
                            "OPENAI_API_KEY": "must-not-be-passed",
                            "OPENAI_BASE_URL": "https://api.openai.com/v1",
                        },
                        "openai/gpt-5.4",
                    ),
                ),
                patch.object(run_agent, "exec_run", side_effect=fake_exec),
                patch.object(run_agent, "copy_to_container") as copy_auth,
                patch.object(run_agent, "_persist_codex_auth") as persist_auth,
                patch.object(run_agent, "_stream_codex_exec", return_value=0) as stream_exec,
            ):
                result = run_agent._execute_codex(
                    "container-id",
                    "find and fix the bug",
                    output_file,
                    _codex_args(auth_file),
                )

            self.assertEqual(result, 0)
            copy_auth.assert_called_once_with(
                "container-id", auth_file.resolve(), "/root/.codex/auth.json"
            )
            persist_auth.assert_called_once_with("container-id", auth_file.resolve())

            self.assertEqual(stream_exec.call_args.args[-1], {})
            all_commands = "\n".join(call[0] for call in exec_calls)
            self.assertNotIn("OPENAI_API_KEY", all_commands)
            self.assertNotIn("model_provider =", all_commands)
            self.assertIn('forced_login_method = "chatgpt"', all_commands)
            self.assertIn("--model gpt-5.4", stream_exec.call_args.args[1])

    def test_codex_output_is_valid_live_jsonl_with_separate_stderr(self) -> None:
        class FakeProcess:
            def __init__(self):
                self.stdout = io.StringIO(
                    '{"type":"turn.started"}\nnot-json-but-preserved\n'
                )

            def wait(self, timeout=None):
                return 0

            def kill(self):
                pass

        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "attempt_1.jsonl"
            stderr_file = Path(temp_dir) / "attempt_1.stderr.log"

            def fake_popen(command, **kwargs):
                kwargs["stderr"].write("diagnostic only\n")
                return FakeProcess()

            console = io.StringIO()
            with (
                patch.object(run_agent.subprocess, "Popen", side_effect=fake_popen),
                redirect_stdout(console),
            ):
                result = run_agent._stream_codex_exec(
                    "container-id",
                    "codex exec --json task",
                    output_file,
                    stderr_file,
                    30,
                    {},
                )

            events = [json.loads(line) for line in output_file.read_text().splitlines()]
            self.assertEqual(result, 0)
            self.assertEqual(events[0]["type"], "turn.started")
            self.assertEqual(events[1]["type"], "runner.output")
            self.assertIn("elapsed_seconds", events[0]["_cybergym"])
            self.assertEqual(stderr_file.read_text(), "diagnostic only\n")
            self.assertNotIn("diagnostic only", output_file.read_text())
            self.assertEqual(len(console.getvalue().splitlines()), 2)

    def test_refreshed_auth_is_replaced_atomically_with_private_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            auth_file = Path(temp_dir) / "auth.json"
            auth_file.write_text('{"old":true}')

            def fake_run(command, **kwargs):
                destination = Path(command[-1])
                destination.write_text('{"tokens":{"access_token":"refreshed"}}')
                return SimpleNamespace(returncode=0, stderr="")

            with patch.object(run_agent.subprocess, "run", side_effect=fake_run):
                run_agent._persist_codex_auth("container-id", auth_file)

            self.assertEqual(
                json.loads(auth_file.read_text()),
                {"tokens": {"access_token": "refreshed"}},
            )
            self.assertEqual(auth_file.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
