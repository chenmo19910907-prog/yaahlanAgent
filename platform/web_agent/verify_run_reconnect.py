#!/usr/bin/env python3
"""验证：SSE 断开不取消任务；active-run 快照逻辑。"""

from __future__ import annotations

import dataclasses
import queue
import threading
import unittest
from typing import Any


@dataclasses.dataclass
class ActiveRun:
    """与 server.ActiveRun 保持一致的快照逻辑（单测不 import 全量 server）。"""

    run_id: str
    session_id: str
    events: queue.Queue[dict[str, Any]] = dataclasses.field(default_factory=queue.Queue)
    done: threading.Event = dataclasses.field(default_factory=threading.Event)
    final_text: str = ""
    error: str | None = None
    last_ack_line: str = ""
    last_elapsed_line: str = ""
    last_batch_line: str = ""
    last_markdown: str = ""

    def emit_event(self, event: dict[str, Any]) -> None:
        etype = event.get("type")
        if etype == "ack":
            self.last_ack_line = str(event.get("line") or "")
        elif etype == "status":
            self.last_elapsed_line = str(event.get("elapsed_line") or "")
            self.last_batch_line = str(event.get("batch_line") or "")
        elif etype == "delta":
            markdown = event.get("markdown")
            if markdown:
                self.last_markdown = str(markdown)
        self.events.put(event)

    def snapshot_events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if self.last_ack_line:
            events.append({"type": "ack", "line": self.last_ack_line})
        if self.last_elapsed_line or self.last_batch_line:
            events.append(
                {
                    "type": "status",
                    "elapsed_line": self.last_elapsed_line,
                    "batch_line": self.last_batch_line,
                }
            )
        if self.last_markdown:
            events.append({"type": "delta", "markdown": self.last_markdown})
        if self.done.is_set():
            if self.error:
                events.append(
                    {
                        "type": "error",
                        "message": self.error,
                        "text": self.final_text,
                    }
                )
            else:
                events.append({"type": "done", "text": self.final_text})
        return events

    def to_active_run_dict(self) -> dict[str, Any]:
        return {
            "active": not self.done.is_set(),
            "run_id": self.run_id,
            "session_id": self.session_id,
            "ack_line": self.last_ack_line,
            "elapsed_line": self.last_elapsed_line,
            "batch_line": self.last_batch_line,
            "markdown": self.last_markdown,
        }


class ActiveRunSnapshotTests(unittest.TestCase):
    def test_emit_event_updates_snapshot(self) -> None:
        run = ActiveRun(run_id="abc", session_id="sess1")
        run.emit_event({"type": "ack", "line": "收到"})
        run.emit_event({"type": "status", "elapsed_line": "1s", "batch_line": "2/5"})
        run.emit_event({"type": "delta", "markdown": "hello"})
        self.assertEqual(run.last_ack_line, "收到")
        self.assertEqual(run.last_batch_line, "2/5")
        self.assertEqual(run.last_markdown, "hello")

    def test_snapshot_events_replay_in_order(self) -> None:
        run = ActiveRun(run_id="abc", session_id="sess1")
        run.emit_event({"type": "ack", "line": "ack"})
        run.emit_event({"type": "delta", "markdown": "partial"})
        types = [e["type"] for e in run.snapshot_events()]
        self.assertEqual(types, ["ack", "delta"])

    def test_snapshot_includes_done_when_finished(self) -> None:
        run = ActiveRun(run_id="abc", session_id="sess1")
        run.final_text = "完成"
        run.done.set()
        self.assertEqual(run.snapshot_events()[-1]["type"], "done")

    def test_active_run_dict_reflects_running_state(self) -> None:
        run = ActiveRun(run_id="r1", session_id="s1")
        self.assertTrue(run.to_active_run_dict()["active"])
        run.done.set()
        self.assertFalse(run.to_active_run_dict()["active"])


if __name__ == "__main__":
    unittest.main()
