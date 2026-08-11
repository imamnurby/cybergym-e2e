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


def _codex_args(auth_file: Path) -> SimpleNamespace:
    return SimpleNamespace(
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
        timeout=30,
    )


class CodexSubscriptionAuthTests(unittest.TestCase):
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

            run_call = next(call for call in exec_calls if call[1] == "Running agent")
            self.assertEqual(run_call[2]["env"], {})
            all_commands = "\n".join(call[0] for call in exec_calls)
            self.assertNotIn("OPENAI_API_KEY", all_commands)
            self.assertNotIn("model_provider =", all_commands)
            self.assertIn('forced_login_method = "chatgpt"', all_commands)
            self.assertIn("--model gpt-5.4", run_call[0])

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
