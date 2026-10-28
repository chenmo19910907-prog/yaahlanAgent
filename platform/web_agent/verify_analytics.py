#!/usr/bin/env python3
"""analytics_store 单测。"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from analytics_store import (
    BJ,
    AnalyticsStore,
    normalize_event_name,
    record_chat_send,
    resolve_usage_custom_range,
    resolve_usage_range,
)


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

    def test_summarize_question_rank(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            store = AnalyticsStore(events_path=path)
            store.record_event(
                event="chat_send",
                staff_id="alice",
                display_name="Alice",
            )
            store.record_event(
                event="chat_send",
                staff_id="alice",
                display_name="Alice",
            )
            store.record_event(
                event="chat_send",
                staff_id="bob",
                display_name="Bob",
            )
            empty_sessions = Path(tmp) / "sessions.json"
            empty_sessions.write_text("{}", encoding="utf-8")
            with patch("analytics_store.SESSIONS_INDEX", empty_sessions):
                rank = store.summarize_question_rank(range_key="30d")
            self.assertEqual(rank["totalRequests"], 3)
            self.assertEqual(rank["userCount"], 2)
            self.assertEqual(rank["items"][0]["staffId"], "alice")
            self.assertEqual(rank["items"][0]["requests"], 2)
            self.assertEqual(rank["items"][0]["displayName"], "Alice")

    def test_question_rank_includes_dingtalk_history_from_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            events_path = tmp_path / "events.jsonl"
            sessions_path = tmp_path / "sessions.json"
            messages_dir = tmp_path / "messages"
            messages_dir.mkdir()
            sid = "dtabc1234567890ab"
            sessions_path.write_text(
                json.dumps(
                    {
                        sid: {
                            "source": "dingtalk",
                            "message_count": 2,
                            "dingtalk_owner_id": "alice",
                            "dingtalk_label": "Alice DT",
                        }
                    }
                ),
                encoding="utf-8",
            )
            messages_dir.joinpath(f"{sid}.json").write_text(
                json.dumps(
                    [
                        {
                            "role": "user",
                            "content": "hi",
                            "timestamp": "2026-08-10T12:00:00+00:00",
                        },
                        {
                            "role": "assistant",
                            "content": "ok",
                            "timestamp": "2026-08-10T12:00:01+00:00",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            store = AnalyticsStore(events_path=events_path)
            fake_now = datetime(2026, 8, 20, 15, 0, 0, tzinfo=BJ)
            with patch("analytics_store.SESSIONS_INDEX", sessions_path):
                with patch("analytics_store.MESSAGES_DIR", messages_dir):
                    with patch("analytics_store._now_bj", return_value=fake_now):
                        rank = store.summarize_question_rank(range_key="30d")
            self.assertEqual(rank["totalRequests"], 1)
            self.assertEqual(rank["items"][0]["staffId"], "alice")
            self.assertEqual(rank["items"][0]["requests"], 1)

    def test_record_chat_send_includes_dingtalk_and_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            with patch("analytics_store.get_analytics_store") as mock_get:
                mock_get.return_value = AnalyticsStore(events_path=path)
                record_chat_send(
                    staff_id="u1",
                    display_name="U1",
                    channel="dingtalk",
                )
                record_chat_send(
                    staff_id="u2",
                    display_name="U2",
                    channel="api",
                )
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            row0 = json.loads(lines[0])
            row1 = json.loads(lines[1])
            self.assertEqual(row0["props"]["channel"], "dingtalk")
            self.assertEqual(row0["page"], "/dingtalk")
            self.assertEqual(row1["props"]["channel"], "api")
            self.assertEqual(row1["page"], "/open-api")


if __name__ == "__main__":
    unittest.main()
