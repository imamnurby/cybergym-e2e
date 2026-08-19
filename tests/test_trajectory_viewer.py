import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from trajectory_viewer import (
    ASSET_DIR,
    PathOutsideRootError,
    TrajectoryViewerServer,
    ViewerConfig,
    discover_sessions,
    parse_jsonl,
    resolve_session_path,
)


def sample_records():
    return [
        {
            "type": "session",
            "id": "session-1",
            "timestamp": "2026-08-16T04:21:45.397Z",
            "cwd": "/src",
        },
        {
            "type": "model_change",
            "timestamp": "2026-08-16T04:21:45.428Z",
            "provider": "openai",
            "modelId": "gpt-test",
        },
        {
            "type": "message",
            "timestamp": "2026-08-16T04:21:45.438Z",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "Find the issue."}],
            },
        },
        {
            "type": "message",
            "timestamp": "2026-08-16T04:21:47.556Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "Inspect the source."},
                    {
                        "type": "toolCall",
                        "id": "call-1",
                        "name": "read",
                        "arguments": {"path": "/src/main.c"},
                    },
                ],
                "usage": {"totalTokens": 120},
            },
        },
        {
            "type": "message",
            "timestamp": "2026-08-16T04:21:48.000Z",
            "message": {
                "role": "toolResult",
                "toolCallId": "call-1",
                "toolName": "read",
                "content": [{"type": "text", "text": "int main(void) {}"}],
                "isError": False,
            },
        },
    ]


def write_session(root: Path, records=None, name="attempt_1.session.jsonl") -> Path:
    path = root / "gpt-test" / "sample_arvo_1" / "20260816_120000_e2e" / "trajectory" / name
    path.parent.mkdir(parents=True)
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in (records or sample_records())),
        encoding="utf-8",
    )
    return path


class DiscoveryTests(unittest.TestCase):
    def test_discovers_sessions_in_task_first_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = write_session(root)
            second = root / "another" / "aaa_task" / "run" / "trajectory" / "attempt_2.session.jsonl"
            second.parent.mkdir(parents=True)
            second.write_text('{"type":"session"}\n', encoding="utf-8")

            sessions = discover_sessions(root)

        self.assertEqual([item["task"] for item in sessions], ["aaa_task", "sample_arvo_1"])
        self.assertEqual(sessions[1]["id"], first.relative_to(root).as_posix())
        self.assertEqual(sessions[1]["model"], "gpt-test")
        self.assertEqual(sessions[1]["attempt"], "attempt_1")

    def test_excludes_symlink_that_escapes_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "root"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            write_session(outside)
            try:
                (root / "escaped").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("Symlinks are not available")

            sessions = discover_sessions(root)

        self.assertEqual(sessions, [])


class PathSafetyTests(unittest.TestCase):
    def test_resolves_valid_relative_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = write_session(root)

            resolved = resolve_session_path(root, path.relative_to(root).as_posix())

        self.assertEqual(resolved, path.resolve())

    def test_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            root.mkdir()

            with self.assertRaises(PathOutsideRootError):
                resolve_session_path(root, "../secret.session.jsonl")

    def test_rejects_non_session_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "notes.txt"
            path.write_text("secret", encoding="utf-8")

            with self.assertRaises(FileNotFoundError):
                resolve_session_path(root, "notes.txt")


class JsonlParsingTests(unittest.TestCase):
    def test_preserves_physical_line_numbers_and_exact_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "attempt_1.session.jsonl"
            path.write_text('{"type": "session"}\n{"type":"message"}\n', encoding="utf-8")

            payload = parse_jsonl(path)

        self.assertEqual(payload["lineCount"], 2)
        self.assertEqual([record["line"] for record in payload["records"]], [1, 2])
        self.assertEqual(payload["records"][0]["raw"], '{"type": "session"}')

    def test_keeps_malformed_lines_and_continues(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "attempt_1.session.jsonl"
            path.write_text('{"type":"session"}\n{"broken":\n{"type":"message"}\n', encoding="utf-8")

            payload = parse_jsonl(path)

        self.assertIsNotNone(payload["records"][1]["parseError"])
        self.assertEqual(payload["records"][2]["data"]["type"], "message")

    def test_returns_only_records_after_requested_line(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = write_session(root)

            payload = parse_jsonl(path, after=3)

        self.assertEqual([record["line"] for record in payload["records"]], [4, 5])
        self.assertEqual(payload["anchorRaw"], json.dumps(sample_records()[2]))

    def test_resets_when_file_was_truncated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = write_session(root, records=sample_records()[:2])

            payload = parse_jsonl(path, after=10)

        self.assertTrue(payload["reset"])
        self.assertEqual(payload["lineCount"], 2)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.session = write_session(self.root)
        self.server = TrajectoryViewerServer(
            ("127.0.0.1", 0), ViewerConfig(root=self.root, asset_dir=ASSET_DIR)
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temporary.cleanup()

    def get(self, path):
        with urlopen(self.base_url + path, timeout=3) as response:
            return response, response.read()

    def test_serves_local_application_with_security_headers(self):
        response, body = self.get("/")

        self.assertEqual(response.status, 200)
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertIn(b"Trajectory viewer", body)
        self.assertNotIn(b"https://cdn", body)

    def test_lists_and_loads_a_session(self):
        _, index_body = self.get("/api/sessions")
        index = json.loads(index_body)
        session_id = index["sessions"][0]["id"]

        _, session_body = self.get(f"/api/session?id={quote(session_id)}")
        payload = json.loads(session_body)

        self.assertEqual(payload["lineCount"], 5)
        self.assertEqual(payload["records"][2]["line"], 3)
        self.assertEqual(payload["records"][2]["data"]["message"]["role"], "user")

    def test_rejects_api_path_traversal(self):
        with self.assertRaises(HTTPError) as raised:
            self.get("/api/session?id=../secret.session.jsonl")

        self.assertEqual(raised.exception.code, 403)

    def test_ui_assets_include_required_navigation_behaviors(self):
        _, javascript = self.get("/app.js")
        source = javascript.decode()

        self.assertIn("function selectLine", source)
        self.assertIn("toolCallId", source)
        self.assertIn("setInterval(refreshCurrentSession, 2000)", source)
        self.assertIn('url.searchParams.set("line"', source)
        self.assertIn("parseLocalJsonl", source)
        self.assertIn("scroll: shouldScroll", source)


if __name__ == "__main__":
    unittest.main()
