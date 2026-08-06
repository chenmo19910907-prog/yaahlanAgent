#!/usr/bin/env python3
"""analytics_store 单测。"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from analytics_store import AnalyticsStore, normalize_event_name


class AnalyticsStoreTest(unittest.TestCase):
    def test_normalize_event_name(self) -> None:
        self.assertEqual(normalize_event_name("Page View"), "page_view")
        self.assertEqual(normalize_event_name(""), "")

    def test_record_and_summarize(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            store = AnalyticsStore(events_path=path)
            ok = store.record_event(
                event="page_view",
                page="/keynote",
                staff_id="alice",
                source="client",
            )
            self.assertTrue(ok)
            store.record_event(
                event="chat_send",
                page="/chat.html",
                staff_id="alice",
                props={"model": "gpt-4"},
            )
            summary = store.summarize(days=7)
            self.assertEqual(summary["total"], 2)
            event_keys = {item["key"] for item in summary["by_event"]}
            self.assertEqual(event_keys, {"page_view", "chat_send"})
            self.assertEqual(summary["by_page"][0]["key"], "/keynote")
            self.assertEqual(summary["page_uv"][0]["uv"], 1)

    def test_summarize_respects_days_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            old_ts = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
            path.write_text(
                json.dumps({"ts": old_ts, "event": "page_view", "page": "/old"}) + "\n",
                encoding="utf-8",
            )
            store = AnalyticsStore(events_path=path)
            summary = store.summarize(days=30)
            self.assertEqual(summary["total"], 0)


if __name__ == "__main__":
    unittest.main()
