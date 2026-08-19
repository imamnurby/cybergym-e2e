#!/usr/bin/env python3
"""Serve a local, read-only browser for Pi session JSONL trajectories."""

from __future__ import annotations

import argparse
import json
import mimetypes
import threading
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import parse_qs, urlparse


ASSET_DIR = Path(__file__).with_name("trajectory_viewer_assets")
SESSION_PATTERN = "attempt_*.session.jsonl"


class PathOutsideRootError(ValueError):
    """Raised when an API path resolves outside the configured results root."""


@dataclass(frozen=True)
class ViewerConfig:
    """Runtime configuration shared by request handlers."""

    root: Path
    asset_dir: Path = ASSET_DIR


def resolve_session_path(root: Path, session_id: str) -> Path:
    """Resolve a relative session identifier without allowing root escapes."""
    resolved_root = root.resolve()
    candidate = (resolved_root / session_id).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as error:
        raise PathOutsideRootError("Session path is outside the configured root") from error
    if not candidate.is_file() or not candidate.name.endswith(".session.jsonl"):
        raise FileNotFoundError("Session file does not exist")
    return candidate


def session_descriptor(root: Path, path: Path) -> dict[str, Any]:
    """Return stable discovery metadata for one native Pi session file."""
    relative = path.resolve().relative_to(root.resolve())
    parts = relative.parts
    model = parts[0] if len(parts) >= 5 else "unknown"
    task = parts[1] if len(parts) >= 5 else path.parent.parent.parent.name
    run = parts[-3] if len(parts) >= 3 else "unknown"
    attempt = path.name.removesuffix(".session.jsonl")
    stat = path.stat()
    return {
        "id": relative.as_posix(),
        "task": task,
        "model": model,
        "run": run,
        "attempt": attempt,
        "size": stat.st_size,
        "modifiedNs": stat.st_mtime_ns,
    }


def discover_sessions(root: Path) -> list[dict[str, Any]]:
    """Discover native session files while excluding symlink escapes."""
    resolved_root = root.resolve()
    sessions: list[dict[str, Any]] = []
    if not resolved_root.is_dir():
        return sessions
    for path in resolved_root.rglob(SESSION_PATTERN):
        try:
            path.resolve().relative_to(resolved_root)
            if path.is_file():
                sessions.append(session_descriptor(resolved_root, path))
        except (OSError, ValueError):
            continue
    return sorted(
        sessions,
        key=lambda item: (
            str(item["task"]).casefold(),
            str(item["model"]).casefold(),
            str(item["run"]),
            str(item["attempt"]),
        ),
    )


def _record_search_text(record: Any, raw: str) -> str:
    if not isinstance(record, dict):
        return raw.casefold()
    message = record.get("message")
    parts: list[str] = [str(record.get("type", ""))]
    if isinstance(message, dict):
        parts.extend(
            str(message.get(key, ""))
            for key in ("role", "toolName", "toolCallId")
        )
        for content in message.get("content", []):
            if isinstance(content, dict):
                parts.extend(
                    str(content.get(key, ""))
                    for key in ("type", "text", "thinking", "name", "arguments")
                )
    parts.append(raw)
    return "\n".join(parts).casefold()


def parse_jsonl(path: Path, after: int = 0) -> dict[str, Any]:
    """Parse physical JSONL records after a given one-based line number."""
    records: list[dict[str, Any]] = []
    total = 0
    anchor_raw: str | None = None
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for total, line_with_newline in enumerate(stream, 1):
            raw = line_with_newline.rstrip("\r\n")
            if total == after:
                anchor_raw = raw
            if total <= after:
                continue
            try:
                parsed = json.loads(raw)
                error = None
            except json.JSONDecodeError as exception:
                parsed = None
                error = {
                    "message": exception.msg,
                    "column": exception.colno,
                }
            records.append(
                {
                    "line": total,
                    "raw": raw,
                    "data": parsed,
                    "parseError": error,
                    "searchText": _record_search_text(parsed, raw),
                }
            )
    stat = path.stat()
    reset = after > total
    if reset:
        return parse_jsonl(path, 0) | {"reset": True}
    return {
        "records": records,
        "lineCount": total,
        "size": stat.st_size,
        "modifiedNs": stat.st_mtime_ns,
        "anchorRaw": anchor_raw,
        "reset": False,
    }


class TrajectoryViewerHandler(BaseHTTPRequestHandler):
    """Serve static assets and the read-only session API."""

    server_version = "TrajectoryViewer/1.0"

    @property
    def config(self) -> ViewerConfig:
        return self.server.viewer_config  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:
        super().log_message(format, *args)

    def _send_bytes(
        self,
        body: bytes,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
        *,
        cache: str = "no-store",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(
        self, payload: Any, status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        request = urlparse(self.path)
        if request.path == "/api/sessions":
            self._send_json(
                {
                    "root": str(self.config.root),
                    "sessions": discover_sessions(self.config.root),
                }
            )
            return
        if request.path == "/api/session":
            self._serve_session(parse_qs(request.query))
            return
        self._serve_asset(request.path)

    def _serve_session(self, query: dict[str, list[str]]) -> None:
        session_id = query.get("id", [""])[0]
        try:
            after = max(0, int(query.get("after", ["0"])[0]))
        except ValueError:
            self._send_error_json(HTTPStatus.BAD_REQUEST, "after must be an integer")
            return
        if not session_id:
            self._send_error_json(HTTPStatus.BAD_REQUEST, "Missing session id")
            return
        try:
            path = resolve_session_path(self.config.root, session_id)
            payload = parse_jsonl(path, after)
            payload["session"] = session_descriptor(self.config.root, path)
            self._send_json(payload)
        except PathOutsideRootError as exception:
            self._send_error_json(HTTPStatus.FORBIDDEN, str(exception))
        except FileNotFoundError as exception:
            self._send_error_json(HTTPStatus.NOT_FOUND, str(exception))
        except OSError as exception:
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exception))

    def _serve_asset(self, request_path: str) -> None:
        name = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        asset_root = self.config.asset_dir.resolve()
        candidate = (asset_root / name).resolve()
        try:
            candidate.relative_to(asset_root)
        except ValueError:
            self._send_error_json(HTTPStatus.FORBIDDEN, "Invalid asset path")
            return
        if not candidate.is_file():
            self._send_error_json(HTTPStatus.NOT_FOUND, "Asset not found")
            return
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {
            "application/javascript",
            "application/json",
        }:
            content_type += "; charset=utf-8"
        self._send_bytes(candidate.read_bytes(), content_type)


class TrajectoryViewerServer(ThreadingHTTPServer):
    """Threaded HTTP server carrying immutable viewer configuration."""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], config: ViewerConfig):
        self.viewer_config = config
        super().__init__(address, TrajectoryViewerHandler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Browse Pi attempt_*.session.jsonl trajectories locally."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("results_pi"),
        help="Results directory to scan (default: results_pi)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=8765, help="Bind port")
    parser.add_argument(
        "--no-browser", action="store_true", help="Do not open a browser window"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"Results root does not exist or is not a directory: {root}")
    if not ASSET_DIR.is_dir():
        raise SystemExit(f"Viewer assets are missing: {ASSET_DIR}")
    server = TrajectoryViewerServer(
        (args.host, args.port), ViewerConfig(root=root)
    )
    actual_host, actual_port = server.server_address[:2]
    browser_host = "127.0.0.1" if actual_host in {"0.0.0.0", "::"} else actual_host
    url = f"http://{browser_host}:{actual_port}/"
    print(f"Trajectory viewer: {url}")
    print(f"Results root: {root}")
    if not args.no_browser:
        threading.Timer(0.25, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping trajectory viewer.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
