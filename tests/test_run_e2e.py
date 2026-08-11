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
        "printf '%s\\n' "
        "'{\"data\":[{\"id\":\"gpt-5.5\"},'"
        "'{\"id\":\"Qwen/Qwen3.6-27B\"}],\"type\":\"model\"}'\n"
    )
    fake_curl.chmod(0o755)

    env = os.environ.copy()
    for name in (
        "AGENT_OUTPUT_DIR",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_MODEL_ID",
        "MAX_BUDGET_PER_TASK",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL_ID",
    ):
        env.pop(name, None)
    env.update(
        {
            "ANTHROPIC_API_KEY": "test-anthropic-key",
            "OPENAI_API_KEY": "test-openai-key",
            "PATH": f"{tmp_path}:{env['PATH']}",
            "PREFLIGHT_ONLY": "1",
        }
    )
    return env


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
            env = _runner_env(Path(temp_dir))
            for preset, agent, provider, model, output_dir, budget in self.PRESETS:
                with self.subTest(preset=preset):
                    result = subprocess.run(
                        ["bash", str(RUNNER), preset],
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
