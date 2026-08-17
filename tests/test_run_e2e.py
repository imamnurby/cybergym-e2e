import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "run_e2e.sh"


def _runner_env(tmp_path: Path) -> dict[str, str]:
    fake_curl = tmp_path / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env bash\n"
        "for arg in \"$@\"; do\n"
        "  case \"$arg\" in\n"
        "    */chat/completions)\n"
        "      printf '%s\\n' "
        "'{\"choices\":[{\"message\":{\"tool_calls\":[{\"function\":{\"name\":\"echo_value\",\"arguments\":\"{\\\"value\\\":\\\"ping\\\"}\"}}]}}]}'\n"
        "      exit 0\n"
        "      ;;\n"
        "  esac\n"
        "done\n"
        "printf '%s\\n' "
        "'{\"data\":[{\"id\":\"gpt-5.5\"},'"
        "'{\"id\":\"gpt-5.4\"},'"
        "'{\"id\":\"Qwen/Qwen3.6-27B\"},'"
        "'{\"id\":\"deepseek-v4-pro\"}],\"type\":\"model\"}'\n"
    )
    fake_curl.chmod(0o755)

    env = os.environ.copy()
    for name in (
        "AGENT_OUTPUT_DIR",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_MODEL_ID",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL_ID",
        "MAX_BUDGET_PER_TASK",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL_ID",
        "CODEX_AUTH_FILE",
        "CODEX_AUTH_MODE",
        "CODEX_REASONING_EFFORT",
        "CODEX_SUPPORTS_REASONING_SUMMARIES",
        "PI_PROVIDER_ID",
        "PI_THINKING_LEVEL",
        "PI_CONTEXT_WINDOW",
        "PI_MAX_OUTPUT_TOKENS",
    ):
        env.pop(name, None)
    env.update(
        {
            "ANTHROPIC_API_KEY": "test-anthropic-key",
            "DEEPSEEK_API_KEY": "test-deepseek-key",
            "OPENAI_API_KEY": "test-openai-key",
            "PATH": f"{tmp_path}:{env['PATH']}",
            "PREFLIGHT_ONLY": "1",
            "CODEX_AUTH_FILE": str(tmp_path / "auth.json"),
        }
    )
    (tmp_path / "auth.json").write_text('{"tokens":{"access_token":"test"}}')
    return env


def _tasks_file(tmp_path: Path) -> Path:
    tasks_file = tmp_path / "instance.txt"
    tasks_file.write_text("example/task\n")
    return tasks_file


class RunE2ETests(unittest.TestCase):
    PRESETS = (
        (
            "qwen",
            "openhands",
            "openai",
            "Qwen/Qwen3.6-27B",
            "agent_output_openhands_qwen",
            "0",
        ),
        (
            "codex-qwen",
            "codex",
            "openai",
            "Qwen/Qwen3.6-27B",
            "agent_output_codex_qwen",
            "0",
        ),
        (
            "pi-qwen",
            "pi",
            "openai",
            "Qwen/Qwen3.6-27B",
            "agent_output_pi_qwen",
            "0",
        ),
        (
            "pi-gpt54",
            "pi",
            "openai",
            "gpt-5.4",
            "agent_output_pi_gpt54",
            "0",
        ),
        (
            "openhands-gpt55",
            "openhands",
            "openai",
            "gpt-5.5",
            "agent_output_openhands_gpt55",
            "10",
        ),
        (
            "codex-gpt55",
            "codex",
            "openai",
            "gpt-5.5",
            "agent_output_codex_gpt55",
            "10",
        ),
        (
            "codex-gpt54-sub",
            "codex",
            "openai",
            "gpt-5.4",
            "agent_output_codex_gpt54_sub",
            "0",
        ),
        (
            "deepseek",
            "openhands",
            "deepseek",
            "deepseek-v4-pro",
            "agent_output_openhands_deepseek",
            "10",
        ),
        (
            "opus45",
            "openhands",
            "anthropic",
            "claude-opus-4-5",
            "agent_output_openhands_opus45",
            "10",
        ),
        (
            "opus46",
            "openhands",
            "anthropic",
            "claude-opus-4-6",
            "agent_output_openhands_opus46",
            "10",
        ),
        (
            "sonnet5",
            "openhands",
            "anthropic",
            "claude-sonnet-5",
            "agent_output_openhands_sonnet5",
            "10",
        ),
    )

    def test_preset_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            env = _runner_env(temp_path)
            tasks_file = _tasks_file(temp_path)
            for preset, agent, provider, model, output_dir, budget in self.PRESETS:
                with self.subTest(preset=preset):
                    command = ["bash", str(RUNNER), preset, str(tasks_file)]
                    if preset == "codex-gpt54-sub":
                        command.append("1")
                    result = subprocess.run(
                        command,
                        cwd=REPO_ROOT,
                        env=env,
                        text=True,
                        capture_output=True,
                        check=False,
                    )

                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(f"Agent: {agent}", result.stdout)
                    self.assertIn(f"Provider: {provider}", result.stdout)
                    self.assertIn(f"Model: {model}", result.stdout)
                    self.assertIn(
                        f"Maximum budget per task: {budget}", result.stdout
                    )
                    self.assertIn(f"Output: {output_dir}", result.stdout)
                    if preset == "codex-qwen":
                        self.assertIn(
                            "Codex reasoning effort: medium", result.stdout
                        )
                    if preset in {"pi-qwen", "pi-gpt54"}:
                        self.assertIn("Pi thinking level: medium", result.stdout)
                        self.assertIn(
                            "Pi context window: 262144", result.stdout
                        )
                        self.assertIn(
                            "Pi maximum output tokens: 128000",
                            result.stdout,
                        )
                    if preset == "pi-qwen":
                        self.assertIn("Pi provider: local-qwen", result.stdout)
                    if preset == "pi-gpt54":
                        self.assertIn("Pi provider: openai", result.stdout)
                    self.assertIn("Tasks: ", result.stdout)
                    self.assertIn("instance.txt", result.stdout)
                    self.assertIn(
                        "Preflight passed. The experiment was not started.",
                        result.stdout,
                    )

    def test_unknown_preset_is_rejected(self) -> None:
        result = subprocess.run(
            ["bash", str(RUNNER), "unknown"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("ERROR: Unknown preset: unknown", result.stderr)

    def test_deepseek_requires_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            env = _runner_env(temp_path)
            env.pop("DEEPSEEK_API_KEY")
            result = subprocess.run(
                [
                    "bash",
                    str(RUNNER),
                    "deepseek",
                    str(_tasks_file(temp_path)),
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR: DEEPSEEK_API_KEY is not set.", result.stderr)

    def test_pi_gpt54_requires_openai_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            env = _runner_env(temp_path)
            env.pop("OPENAI_API_KEY")
            result = subprocess.run(
                [
                    "bash",
                    str(RUNNER),
                    "pi-gpt54",
                    str(_tasks_file(temp_path)),
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR: OPENAI_API_KEY is not set.", result.stderr)

    def test_pi_limits_accept_explicit_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            env = _runner_env(temp_path)
            env["PI_CONTEXT_WINDOW"] = "196608"
            env["PI_MAX_OUTPUT_TOKENS"] = "32768"
            result = subprocess.run(
                [
                    "bash",
                    str(RUNNER),
                    "pi-gpt54",
                    str(_tasks_file(temp_path)),
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Pi context window: 196608", result.stdout)
        self.assertIn(
            "Pi maximum output tokens: 32768", result.stdout
        )

    def test_pi_rejects_output_limit_above_context_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            env = _runner_env(temp_path)
            env["PI_CONTEXT_WINDOW"] = "32768"
            env["PI_MAX_OUTPUT_TOKENS"] = "32769"
            result = subprocess.run(
                [
                    "bash",
                    str(RUNNER),
                    "pi-qwen",
                    str(_tasks_file(temp_path)),
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "PI_MAX_OUTPUT_TOKENS cannot exceed PI_CONTEXT_WINDOW",
            result.stderr,
        )

    def test_subscription_auth_requires_a_nonempty_auth_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            env = _runner_env(temp_path)
            Path(env["CODEX_AUTH_FILE"]).unlink()
            result = subprocess.run(
                [
                    "bash",
                    str(RUNNER),
                    "codex-gpt54-sub",
                    str(_tasks_file(temp_path)),
                    "1",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Codex auth file does not exist or is empty", result.stderr)

    def test_subscription_auth_rejects_parallel_workers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            env = _runner_env(temp_path)
            result = subprocess.run(
                [
                    "bash",
                    str(RUNNER),
                    "codex-gpt54-sub",
                    str(_tasks_file(temp_path)),
                    "2",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("requires max_parallel=1", result.stderr)

    def test_invalid_worker_count_is_rejected(self) -> None:
        for max_parallel in ("0", "two", "-1"):
            with self.subTest(max_parallel=max_parallel):
                result = subprocess.run(
                    ["bash", str(RUNNER), "qwen", "instance.txt", max_parallel],
                    cwd=REPO_ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )

                self.assertEqual(result.returncode, 2)
                self.assertIn(
                    "max_parallel must be a positive integer", result.stderr
                )


if __name__ == "__main__":
    unittest.main()
