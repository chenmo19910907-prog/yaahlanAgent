#!/usr/bin/env python3
"""analytics_store 单测。"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from analytics_store import BJ, AnalyticsStore, normalize_event_name, resolve_usage_custom_range, resolve_usage_range


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

    def test_resolve_usage_range_month(self) -> None:
        start, end, label, key = resolve_usage_range("month")
        self.assertEqual(key, "month")
        self.assertEqual(label, "本月")
        self.assertLess(start, end)

    def test_resolve_usage_range_yesterday(self) -> None:
        fake_now = datetime(2026, 8, 20, 15, 0, 0, tzinfo=BJ)
        with patch("analytics_store._now_bj", return_value=fake_now):
            start, end, label, key = resolve_usage_range("yesterday")
        self.assertEqual(key, "yesterday")
        self.assertEqual(label, "昨日")
        start_bj = start.astimezone(BJ)
        end_bj = end.astimezone(BJ)
        self.assertEqual(start_bj.strftime("%Y-%m-%d"), "2026-08-19")
        self.assertEqual(end_bj.strftime("%Y-%m-%d"), "2026-08-19")

    def test_resolve_usage_range_last_week(self) -> None:
        fake_now = datetime(2026, 8, 20, 15, 0, 0, tzinfo=BJ)
        with patch("analytics_store._now_bj", return_value=fake_now):
            start, end, label, key = resolve_usage_range("7d")
        self.assertEqual(key, "7d")
        self.assertEqual(label, "上周")
        start_bj = start.astimezone(BJ)
        end_bj = end.astimezone(BJ)
        self.assertEqual(start_bj.strftime("%Y-%m-%d"), "2026-08-10")
        self.assertEqual(end_bj.strftime("%Y-%m-%d"), "2026-08-16")
        self.assertEqual((end_bj - start_bj).days, 6)

    def test_resolve_usage_range_last_month(self) -> None:
        fake_now = datetime(2026, 8, 20, 15, 0, 0, tzinfo=BJ)
        with patch("analytics_store._now_bj", return_value=fake_now):
            start, end, label, key = resolve_usage_range("last_month")
        self.assertEqual(key, "last_month")
        self.assertEqual(label, "上月")
        start_bj = start.astimezone(BJ)
        end_bj = end.astimezone(BJ)
        self.assertEqual(start_bj.strftime("%Y-%m-%d"), "2026-07-01")
        self.assertEqual(end_bj.strftime("%Y-%m-%d"), "2026-07-31")

    def test_resolve_usage_custom_range(self) -> None:
        fake_now = datetime(2026, 8, 20, 15, 0, 0, tzinfo=BJ)
        with patch("analytics_store._now_bj", return_value=fake_now):
            start, end, label, key = resolve_usage_custom_range("2026-08-01", "2026-08-10")
        self.assertEqual(label, "2026-08-01 至 2026-08-10")
        self.assertEqual(key, "custom:2026-08-01:2026-08-10")
        start_bj = start.astimezone(BJ)
        end_bj = end.astimezone(BJ)
        self.assertEqual(start_bj.strftime("%Y-%m-%d"), "2026-08-01")
        self.assertEqual(end_bj.strftime("%Y-%m-%d"), "2026-08-10")

    def test_resolve_usage_custom_range_rejects_long_span(self) -> None:
        fake_now = datetime(2026, 8, 20, 15, 0, 0, tzinfo=BJ)
        with patch("analytics_store._now_bj", return_value=fake_now):
            with self.assertRaises(ValueError):
                resolve_usage_custom_range("2026-01-01", "2026-08-20")

    def test_summarize_user_usage_requests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            store = AnalyticsStore(events_path=path)
            store.record_event(
                event="chat_send",
                page="/chat.html",
                staff_id="alice",
                props={"model": "composer-2.5"},
            )
            summary = store.summarize_user_usage("alice", range_key="30d")
            self.assertEqual(summary["requests"], 1)
            self.assertEqual(summary["range"], "30d")
            self.assertEqual(summary["rangeLabel"], "30天内")

    def test_summarize_user_usage_other_user_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            store = AnalyticsStore(events_path=path)
            store.record_event(event="chat_send", staff_id="alice")
            store.record_event(event="chat_send", staff_id="bob")
            summary = store.summarize_user_usage("alice", range_key="month")
            self.assertEqual(summary["requests"], 1)


if __name__ == "__main__":
    unittest.main()
