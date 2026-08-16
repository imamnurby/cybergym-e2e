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


def _pi_args(**overrides) -> SimpleNamespace:
    values = dict(
        model_provider="openai",
        litellm_model_id="openai/gpt-5.2-codex",
        openai_model_id="Qwen/Qwen3.6-27B",
        deepseek_model_id="deepseek-v4-pro",
        bedrock_model_id="bedrock-model",
        anthropic_model_id="anthropic-model",
        aws_region="us-west-2",
        aws_profile=None,
        max_budget_per_task=0,
        pi_provider_id="local-qwen",
        pi_thinking_level="medium",
        timeout=30,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class PiIntegrationTests(unittest.TestCase):
    def test_pi_qwen_configuration_and_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "attempt_1.jsonl"
            exec_calls = []

            def fake_exec(container_id, command, description=None, **kwargs):
                exec_calls.append((command, description, kwargs))
                return 0, "", ""

            qwen_env = {
                "OPENAI_API_KEY": "EMPTY",
                "OPENAI_BASE_URL": "http://172.17.0.1:8100/v1",
            }
            with (
                patch.object(
                    run_agent,
                    "get_llm_env",
                    return_value=(qwen_env, "openai/Qwen/Qwen3.6-27B"),
                ),
                patch.object(run_agent, "exec_run", side_effect=fake_exec),
                patch.object(
                    run_agent, "_stream_json_exec", return_value=0
                ) as stream_exec,
                patch.object(
                    run_agent, "_copy_pi_session", return_value=True
                ) as copy_session,
            ):
                result = run_agent._execute_pi(
                    "container-id",
                    "find and fix the bug",
                    output_file,
                    _pi_args(),
                )

            self.assertEqual(result, 0)
            config_command = exec_calls[0][0]
            config_text = config_command[
                config_command.index("{\n") : config_command.rindex(
                    "\nPI_MODELS_EOF"
                )
            ]
            config = json.loads(config_text)
            provider = config["providers"]["local-qwen"]
            model = provider["models"][0]
            self.assertEqual(provider["api"], "openai-completions")
            self.assertEqual(provider["apiKey"], "$OPENAI_API_KEY")
            self.assertFalse(provider["compat"]["supportsDeveloperRole"])
            self.assertEqual(
                provider["compat"]["thinkingFormat"], "qwen-chat-template"
            )
            self.assertEqual(model["contextWindow"], 262144)
            self.assertEqual(model["maxTokens"], 131072)

            command = stream_exec.call_args.args[1]
            self.assertIn("--mode json", command)
            self.assertIn("--provider local-qwen", command)
            self.assertIn("--model Qwen/Qwen3.6-27B", command)
            self.assertIn("--thinking medium", command)
            self.assertIn("--tools read,bash,edit,write,grep,find,ls", command)
            self.assertIn("--no-extensions --no-skills", command)
            self.assertIn("--no-prompt-templates", command)
            env = stream_exec.call_args.args[5]
            self.assertEqual(env["PI_OFFLINE"], "1")
            self.assertEqual(env["PI_SKIP_VERSION_CHECK"], "1")
            self.assertEqual(env["PI_TELEMETRY"], "0")
            copy_session.assert_called_once_with(
                "container-id",
                str(Path(temp_dir) / "attempt_1.session.jsonl"),
            )

    def test_pi_openai_configuration_and_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "attempt_1.jsonl"
            exec_calls = []

            def fake_exec(container_id, command, description=None, **kwargs):
                exec_calls.append((command, description, kwargs))
                return 0, "", ""

            openai_env = {
                "OPENAI_API_KEY": "test-openai-key",
                "OPENAI_BASE_URL": "https://api.openai.com/v1",
            }
            with (
                patch.object(
                    run_agent,
                    "get_llm_env",
                    return_value=(openai_env, "openai/gpt-5.4"),
                ),
                patch.object(run_agent, "exec_run", side_effect=fake_exec),
                patch.object(
                    run_agent, "_stream_json_exec", return_value=0
                ) as stream_exec,
                patch.object(
                    run_agent, "_copy_pi_session", return_value=True
                ),
            ):
                result = run_agent._execute_pi(
                    "container-id",
                    "find and fix the bug",
                    output_file,
                    _pi_args(
                        openai_model_id="gpt-5.4",
                        pi_provider_id="openai",
                    ),
                )

            self.assertEqual(result, 0)
            self.assertEqual(len(exec_calls), 1)
            self.assertNotIn("models.json", exec_calls[0][0])
            command = stream_exec.call_args.args[1]
            self.assertIn("--provider openai", command)
            self.assertIn("--model gpt-5.4", command)
            self.assertIn("--thinking medium", command)
            env = stream_exec.call_args.args[5]
            self.assertEqual(env["OPENAI_API_KEY"], "test-openai-key")

    def test_pi_requires_openai_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(RuntimeError, "requires.*openai"):
                run_agent._execute_pi(
                    "container-id",
                    "task",
                    Path(temp_dir) / "attempt.jsonl",
                    _pi_args(model_provider="anthropic"),
                )

    def test_pi_installer_pins_stable_version(self) -> None:
        installer = SCRIPTS_DIR / "install_pi.sh"
        self.assertIn(
            "@earendil-works/pi-coding-agent@0.84.1",
            installer.read_text(),
        )


if __name__ == "__main__":
    unittest.main()
