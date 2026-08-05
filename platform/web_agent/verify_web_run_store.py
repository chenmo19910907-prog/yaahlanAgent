#!/usr/bin/env python3
"""web_run_store 单测。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_AGENT_DIR))

from web_run_store import (  # noqa: E402
    RUN_STATUS_DONE,
    RUN_STATUS_RUNNING,
    RunMeta,
    WebRunStore,
)


class WebRunStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = WebRunStore(root=Path(self._tmp.name) / "runs")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _sample_meta(self, run_id: str = "abc123", session_id: str = "sess1") -> RunMeta:
        return RunMeta(
            run_id=run_id,
            session_id=session_id,
            message="hello",
            display_message="hello",
            model="composer",
            enabled_external_agents=[],
            author_id="u1",
            author_label="User",
            image_paths=[],
            file_paths=[],
            attachment_names=[],
            worker_pid=99999,
            status=RUN_STATUS_RUNNING,
            started_at=1.0,
        )

    def test_create_and_get_run(self) -> None:
        meta = self._sample_meta()
        self.store.create_run(meta)
        loaded = self.store.get_run("abc123")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.session_id, "sess1")
        self.assertEqual(loaded.status, RUN_STATUS_RUNNING)

    def test_append_event_updates_snapshot(self) -> None:
        self.store.create_run(self._sample_meta())
        self.store.append_event("abc123", {"type": "delta", "markdown": "partial"})
        snap = self.store.get_snapshot("abc123")
        self.assertEqual(snap.last_markdown, "partial")

    def test_append_delta_persists_process(self) -> None:
        self.store.create_run(self._sample_meta())
        proc = {"thinking": "先查 Admin", "tools": ["Shell"]}
        self.store.append_event(
            "abc123",
            {"type": "delta", "markdown": "### 思考中\n\n先查 Admin", "process": proc},
        )
        snap = self.store.get_snapshot("abc123")
        self.assertEqual(snap.last_process, proc)

    def test_append_delta_merges_longer_process(self) -> None:
        self.store.create_run(self._sample_meta())
        self.store.append_event(
            "abc123",
            {"type": "delta", "process": {"thinking": "正在全面排查", "tools": []}},
        )
        self.store.append_event(
            "abc123",
            {"type": "delta", "process": {"thinking": "正在", "tools": ["Shell"]}},
        )
        snap = self.store.get_snapshot("abc123")
        self.assertEqual(snap.last_process["thinking"], "正在全面排查")
        self.assertEqual(snap.last_process["tools"], ["Shell"])

    def test_read_new_events_advances_tail(self) -> None:
        self.store.create_run(self._sample_meta())
        self.store.append_event("abc123", {"type": "ack", "line": "收到"})
        first, _ = self.store.read_new_events("abc123")
        second, _ = self.store.read_new_events("abc123")
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)

    def test_find_active_by_session(self) -> None:
        self.store.create_run(self._sample_meta())
        found = self.store.find_active_by_session("sess1")
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.run_id, "abc123")
        self.store.mark_status("abc123", RUN_STATUS_DONE)
        self.assertIsNone(self.store.find_active_by_session("sess1"))

    def test_cancel_flag(self) -> None:
        self.store.create_run(self._sample_meta())
        self.assertFalse(self.store.is_cancel_requested("abc123"))
        self.store.request_cancel("abc123")
        self.assertTrue(self.store.is_cancel_requested("abc123"))


if __name__ == "__main__":
    unittest.main()
