import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tracjectory_extractor.codex_runner import CodexConfig, CodexRunner


class CodexRunnerTests(unittest.TestCase):
    def test_uses_writable_isolated_state_and_preserves_refreshed_authentication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_home = root / "source-codex-home"
            source_home.mkdir()
            source_auth = source_home / "auth.json"
            source_auth.write_text('{"token":"original"}', encoding="utf-8")
            schema = root / "schema.json"
            schema.write_text('{"type":"object"}', encoding="utf-8")
            calls = []

            def fake_run(command, **kwargs):
                calls.append(command)
                isolated_home = Path(kwargs["env"]["CODEX_HOME"])
                authentication = isolated_home / "auth.json"
                expected = "original" if len(calls) == 1 else "refreshed"
                self.assertEqual(
                    json.loads(authentication.read_text(encoding="utf-8"))["token"],
                    expected,
                )
                self.assertNotEqual(isolated_home, source_home)
                self.assertEqual(authentication.stat().st_mode & 0o777, 0o600)
                authentication.write_text('{"token":"refreshed"}', encoding="utf-8")
                response_path = Path(
                    command[command.index("--output-last-message") + 1]
                )
                response_path.write_text('{"result":"ok"}', encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch.dict(os.environ, {"CODEX_HOME": str(source_home)}):
                with patch(
                    "tracjectory_extractor.codex_runner.subprocess.run",
                    side_effect=fake_run,
                ):
                    with CodexRunner(CodexConfig(model="luna")) as runner:
                        self.assertEqual(runner.run("first", schema), {"result": "ok"})
                        self.assertEqual(runner.run("second", schema), {"result": "ok"})

            self.assertEqual(len(calls), 2)
            self.assertIn("--ignore-user-config", calls[0])
            self.assertEqual(calls[0][calls[0].index("--model") + 1], "gpt-5.6-luna")
            self.assertEqual(
                json.loads(source_auth.read_text(encoding="utf-8"))["token"],
                "original",
            )


if __name__ == "__main__":
    unittest.main()
