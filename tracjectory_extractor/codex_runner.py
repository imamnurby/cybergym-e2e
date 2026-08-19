"""Machine-readable Codex execution for ontology induction."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import weakref
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)
MODEL_ALIASES = {
    "luna": "gpt-5.6-luna",
    "terra": "gpt-5.6-terra",
    "sol": "gpt-5.6-sol",
}


@dataclass(frozen=True)
class CodexConfig:
    executable: str = "codex"
    model: str = "gpt-5.6-luna"
    reasoning_effort: str = "xhigh"
    timeout_seconds: int = 1800
    reuse_checkpoints_across_reasoning: bool = False


class CodexRunner:
    """Run Codex in an empty read-only workspace with a required JSON schema."""

    def __init__(self, config: CodexConfig | None = None) -> None:
        selected = config or CodexConfig()
        resolved_model = MODEL_ALIASES.get(selected.model, selected.model)
        if resolved_model != selected.model:
            LOGGER.warning(
                "Model alias %r resolved to supported model ID %r",
                selected.model,
                resolved_model,
            )
        self.config = replace(selected, model=resolved_model)
        self._codex_home = Path(tempfile.mkdtemp(prefix="trajectory-codex-home-"))
        self._cleanup = weakref.finalize(
            self, shutil.rmtree, self._codex_home, ignore_errors=True
        )
        self._copy_authentication()

    def __enter__(self) -> CodexRunner:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._cleanup()

    def _copy_authentication(self) -> None:
        configured_home = os.environ.get("CODEX_HOME")
        source_home = (
            Path(configured_home).expanduser()
            if configured_home
            else Path.home() / ".codex"
        )
        source = source_home / "auth.json"
        if not source.is_file():
            return
        destination = self._codex_home / "auth.json"
        shutil.copyfile(source, destination)
        destination.chmod(0o600)

    def run(self, prompt: str, schema_path: Path) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="trajectory-coding-") as directory:
            work_dir = Path(directory)
            response_path = work_dir / "response.json"
            command = [
                self.config.executable,
                "exec",
                "--model",
                self.config.model,
                "-c",
                f'model_reasoning_effort="{self.config.reasoning_effort}"',
                "--sandbox",
                "read-only",
                "--ephemeral",
                "--ignore-user-config",
                "--skip-git-repo-check",
                "--output-schema",
                str(schema_path.resolve()),
                "--output-last-message",
                str(response_path),
                "--cd",
                str(work_dir),
                "-",
            ]
            environment = os.environ.copy()
            environment["CODEX_HOME"] = str(self._codex_home)
            LOGGER.info(
                "Codex request started: schema=%s model=%s reasoning=%s timeout=%ss",
                schema_path.name,
                self.config.model,
                self.config.reasoning_effort,
                self.config.timeout_seconds,
            )
            started_at = time.monotonic()
            try:
                result = subprocess.run(
                    command,
                    input=prompt,
                    text=True,
                    capture_output=True,
                    env=environment,
                    timeout=self.config.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                LOGGER.error(
                    "Codex request timed out after %.1fs: schema=%s",
                    time.monotonic() - started_at,
                    schema_path.name,
                )
                raise
            if result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip()
                LOGGER.error(
                    "Codex request failed after %.1fs: schema=%s exit_code=%s",
                    time.monotonic() - started_at,
                    schema_path.name,
                    result.returncode,
                )
                raise RuntimeError(
                    f"Codex exited with {result.returncode}: {detail[-2000:]}"
                )
            if not response_path.is_file():
                raise RuntimeError("Codex did not write its final structured response")
            try:
                value = json.loads(response_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                raise RuntimeError("Codex returned invalid JSON") from error
            if not isinstance(value, dict):
                raise RuntimeError("Codex response must be a JSON object")
            LOGGER.info(
                "Codex request completed in %.1fs: schema=%s",
                time.monotonic() - started_at,
                schema_path.name,
            )
            return value
