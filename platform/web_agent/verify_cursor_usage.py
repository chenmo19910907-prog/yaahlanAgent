#!/usr/bin/env python3
"""cursor_usage / cursor_usage_store 单测。"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from cursor_usage import (
    CursorAuthError,
    _accumulate_event_daily,
    _event_tokens,
    _fetch_admin_usage,
    _fetch_dashboard_usage,
    _normalize_session_token,
    _split_span_chunks,
    build_daily_series,
    clear_user_today_live_cache,
    dashboard_usage_url,
    get_usage_date_bounds,
    parse_cursor_session_input,
    summarize_user_usage,
)
from analytics_store import BJ
from cursor_usage_store import CursorUsageCredentialStore


class CursorUsageStoreTest(unittest.TestCase):
    def test_upsert_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CursorUsageCredentialStore(path=Path(tmp) / "creds.json")
            status = store.upsert("alice", session_token="token-a")
            self.assertTrue(status["configured"])
            self.assertTrue(status["hasSessionToken"])
            creds = store.get_credentials("alice")
            self.assertEqual(creds["sessionToken"], "token-a")

    def test_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CursorUsageCredentialStore(path=Path(tmp) / "creds.json")
            store.upsert("alice", cursor_email="alice@example.com")
            status = store.clear("alice")
            self.assertFalse(status["configured"])


class CursorUsageTest(unittest.TestCase):
    def setUp(self) -> None:
        clear_user_today_live_cache("alice")

    def test_event_tokens(self) -> None:
        total = _event_tokens(
            {
                "tokenUsage": {
                    "inputTokens": 10,
                    "outputTokens": 20,
                    "cacheWriteTokens": 5,
                    "cacheReadTokens": 3,
                }
            }
        )
        self.assertEqual(total, 38)

    def test_dashboard_usage_url(self) -> None:
        start = datetime(2026, 7, 15, tzinfo=timezone.utc)
        end = datetime(2026, 8, 13, tzinfo=timezone.utc)
        url = dashboard_usage_url(start, end)
        self.assertIn("startDate=2026-07-15", url)
        self.assertIn("endDate=2026-08-13", url)

    def test_get_usage_date_bounds_from_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from cursor_usage_daily_store import CursorUsageDailyStore

            daily_path = Path(tmp) / "daily.json"
            store = CursorUsageDailyStore(path=daily_path)
            store.set_days(
                "alice",
                {
                    "2026-02-20": {"requests": 0, "tokens": 0},
                    "2026-03-01": {"requests": 2, "tokens": 20},
                    "2026-07-01": {"requests": 0, "tokens": 0},
                },
            )
            fake_now = datetime(2026, 8, 20, 15, 0, 0, tzinfo=BJ)
            with patch("cursor_usage.get_cursor_usage_daily_store", return_value=store):
                with patch("cursor_usage.datetime") as dt_mock:
                    dt_mock.now.return_value = fake_now
                    bounds = get_usage_date_bounds("alice")
            self.assertEqual(bounds["maxDate"], "2026-08-20")
            self.assertEqual(bounds["minDate"], "2026-03-01")
            self.assertEqual(bounds["earliestWithData"], "2026-03-01")
            self.assertEqual(bounds["preloadDays"], 180)
            trimmed = store.get_day("alice", "2026-02-20")
            self.assertIsNone(trimmed)

    def test_split_span_chunks(self) -> None:
        days = [f"2026-01-{d:02d}" for d in range(1, 32)]
        days += [f"2026-02-{d:02d}" for d in range(1, 29)]
        chunks = _split_span_chunks(days, max_days=28)
        self.assertEqual(len(chunks), 3)
        self.assertEqual(sum(len(c) for c in chunks), len(days))

    def test_summarize_custom_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from cursor_usage_daily_store import CursorUsageDailyStore

            cred_store = CursorUsageCredentialStore(path=Path(tmp) / "creds.json")
            daily_store = CursorUsageDailyStore(path=Path(tmp) / "daily.json")
            cred_store.upsert("alice", session_token="token-a")
            daily_store.set_days(
                "alice",
                {
                    "2026-08-10": {"requests": 3, "tokens": 30},
                    "2026-08-11": {"requests": 2, "tokens": 20},
                },
            )
            fake_now = datetime(2026, 8, 20, 15, 0, 0, tzinfo=BJ)
            with patch("cursor_usage.get_cursor_usage_store", return_value=cred_store):
                with patch("cursor_usage.get_cursor_usage_daily_store", return_value=daily_store):
                    with patch("cursor_usage.load_env_local"):
                        with patch.dict("os.environ", {}, clear=True):
                            with patch("cursor_usage.datetime") as dt_mock:
                                dt_mock.now.return_value = fake_now
                                summary = summarize_user_usage(
                                    "alice",
                                    start_date="2026-08-10",
                                    end_date="2026-08-11",
                                )
            self.assertEqual(summary["requests"], 5)
            self.assertEqual(summary["tokens"], 50)
            self.assertEqual(summary["rangeLabel"], "2026-08-10 至 2026-08-11")
            self.assertEqual(len(summary["daily"]), 2)

    def test_summarize_needs_setup_without_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CursorUsageCredentialStore(path=Path(tmp) / "creds.json")
            with patch("cursor_usage.get_cursor_usage_store", return_value=store):
                with patch("cursor_usage.load_env_local"):
                    with patch.dict("os.environ", {}, clear=True):
                        summary = summarize_user_usage("alice", range_key="month")
            self.assertTrue(summary["needsSetup"])
            self.assertEqual(summary["source"], "cursor_dashboard")

    def test_fetch_dashboard_usage_aggregates(self) -> None:
        page1 = {
            "totalUsageEventsCount": 2,
            "usageEventsDisplay": [
                {
                    "timestamp": "1780000000000",
                    "tokenUsage": {"inputTokens": 1, "outputTokens": 2},
                },
                {
                    "timestamp": "1780086400000",
                    "tokenUsage": {"inputTokens": 3, "outputTokens": 4},
                },
            ],
        }
        with patch("cursor_usage._http_json", return_value=page1):
            stats = _fetch_dashboard_usage("token", start_ms=1, end_ms=2)
        self.assertEqual(stats["requests"], 2)
        self.assertEqual(stats["tokens"], 10)
        self.assertEqual(stats["daily"]["2026-05-29"]["requests"], 1)
        self.assertEqual(stats["daily"]["2026-05-30"]["requests"], 1)

    def test_build_daily_series_fills_range(self) -> None:
        start = datetime(2026, 8, 11, tzinfo=timezone.utc)
        end = datetime(2026, 8, 13, tzinfo=timezone.utc)
        rows = build_daily_series(
            start,
            end,
            {"2026-08-12": {"requests": 5, "tokens": 100}},
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1]["requests"], 5)
        self.assertEqual(rows[1]["tokens"], 100)
        self.assertEqual(rows[0]["requests"], 0)

    def test_fetch_admin_usage_aggregates(self) -> None:
        page1 = {
            "totalUsageEventsCount": 1,
            "usageEvents": [
                {
                    "timestamp": "1780000000000",
                    "tokenUsage": {"inputTokens": 5, "outputTokens": 6},
                }
            ],
            "pagination": {"hasNextPage": False},
        }
        with patch("cursor_usage._http_json", return_value=page1):
            stats = _fetch_admin_usage("key", email="dev@example.com", start_ms=1, end_ms=2)
        self.assertEqual(stats["requests"], 1)
        self.assertEqual(stats["tokens"], 11)
        self.assertEqual(stats["daily"]["2026-05-29"]["tokens"], 11)

    def test_accumulate_event_daily(self) -> None:
        daily: dict[str, dict[str, int]] = {}
        _accumulate_event_daily(
            daily,
            {
                "timestamp": "1780000000000",
                "tokenUsage": {"inputTokens": 2, "outputTokens": 3},
            },
        )
        self.assertEqual(daily["2026-05-29"]["requests"], 1)
        self.assertEqual(daily["2026-05-29"]["tokens"], 5)

    def test_normalize_session_token(self) -> None:
        self.assertEqual(
            _normalize_session_token("WorkosCursorSessionToken=abc%3A%3Ajwt"),
            "abc%3A%3Ajwt",
        )
        self.assertEqual(_normalize_session_token("  token-value  "), "token-value")
        self.assertEqual(
            _normalize_session_token("user_01::jwt.part.here"),
            "user_01%3A%3Ajwt.part.here",
        )

    def test_parse_cookie_blob(self) -> None:
        blob = (
            "WorkosCursorSessionToken=user_01%3A%3Ajwt; "
            "team_id=13421981; workos_id=user_01"
        )
        parsed = parse_cursor_session_input(blob)
        self.assertEqual(parsed["sessionToken"], "user_01%3A%3Ajwt")
        self.assertEqual(parsed["teamId"], "13421981")
        self.assertEqual(parsed["workosId"], "user_01")

    def test_summarize_reauth_on_dashboard_auth_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from cursor_usage_daily_store import CursorUsageDailyStore

            store = CursorUsageCredentialStore(path=Path(tmp) / "creds.json")
            daily_store = CursorUsageDailyStore(path=Path(tmp) / "daily.json")
            store.upsert("alice", session_token="expired-token")
            with patch("cursor_usage.get_cursor_usage_store", return_value=store):
                with patch("cursor_usage.get_cursor_usage_daily_store", return_value=daily_store):
                    with patch("cursor_usage.load_env_local"):
                        with patch.dict("os.environ", {}, clear=True):
                            with patch(
                                "cursor_usage._fetch_dashboard_usage",
                                side_effect=CursorAuthError("会话过期"),
                            ):
                                summary = summarize_user_usage("alice", range_key="month")
            self.assertTrue(summary["needsReauth"])
            self.assertIn("过期", summary["error"])

    def test_summarize_admin_fallback_when_dashboard_auth_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from cursor_usage_daily_store import CursorUsageDailyStore

            store = CursorUsageCredentialStore(path=Path(tmp) / "creds.json")
            daily_store = CursorUsageDailyStore(path=Path(tmp) / "daily.json")
            store.upsert("alice", session_token="expired-token", cursor_email="alice@example.com")
            fake_now = datetime(2026, 8, 20, 15, 0, 0, tzinfo=BJ)
            with patch("cursor_usage.get_cursor_usage_store", return_value=store):
                with patch("cursor_usage.get_cursor_usage_daily_store", return_value=daily_store):
                    with patch("cursor_usage.load_env_local"):
                        with patch.dict(
                            "os.environ",
                            {"CURSOR_API_KEY": "cursor_test_key"},
                            clear=True,
                        ):
                            with patch("analytics_store._now_bj", return_value=fake_now):
                                with patch("cursor_usage._today_key_bj", return_value="2026-08-20"):
                                    with patch(
                                        "cursor_usage._fetch_dashboard_usage",
                                        side_effect=CursorAuthError("会话过期"),
                                    ):
                                        with patch(
                                            "cursor_usage._fetch_admin_usage",
                                            return_value={
                                                "requests": 3,
                                                "tokens": 30,
                                                "daily": {
                                                    "2026-08-20": {
                                                        "requests": 3,
                                                        "tokens": 30,
                                                    }
                                                },
                                            },
                                        ):
                                            summary = summarize_user_usage("alice", range_key="day")
            self.assertEqual(summary["requests"], 3)
            self.assertEqual(summary["tokens"], 30)
            self.assertEqual(summary["source"], "cursor_admin_api")

    def test_today_cached_until_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from cursor_usage_daily_store import CursorUsageDailyStore

            cred_store = CursorUsageCredentialStore(path=Path(tmp) / "creds.json")
            daily_store = CursorUsageDailyStore(path=Path(tmp) / "daily.json")
            cred_store.upsert("alice", session_token="token-a")
            fake_now = datetime(2026, 8, 20, 15, 0, 0, tzinfo=BJ)
            fetch_mock = MagicMock(
                return_value=(
                    "cursor_dashboard",
                    None,
                    {"2026-08-20": {"requests": 5, "tokens": 50}},
                )
            )
            with patch("cursor_usage.get_cursor_usage_store", return_value=cred_store):
                with patch("cursor_usage.get_cursor_usage_daily_store", return_value=daily_store):
                    with patch("cursor_usage.load_env_local"):
                        with patch.dict("os.environ", {}, clear=True):
                            with patch("cursor_usage.datetime") as dt_mock:
                                dt_mock.now.return_value = fake_now
                                with patch("cursor_usage._today_key_bj", return_value="2026-08-20"):
                                    with patch(
                                        "cursor_usage._fetch_and_cache_days",
                                        fetch_mock,
                                    ):
                                        first = summarize_user_usage(
                                            "alice",
                                            range_key="day",
                                            refresh=True,
                                        )
                                        self.assertEqual(fetch_mock.call_count, 1)
                                        second = summarize_user_usage(
                                            "alice",
                                            range_key="day",
                                            refresh=False,
                                        )
                                        self.assertEqual(fetch_mock.call_count, 1)
                                        fetch_mock.reset_mock()
                                        third = summarize_user_usage(
                                            "alice",
                                            range_key="day",
                                            refresh=True,
                                        )
                                        self.assertEqual(fetch_mock.call_count, 1)
            self.assertEqual(first["requests"], 5)
            self.assertEqual(second["requests"], 5)
            self.assertEqual(third["requests"], 5)


if __name__ == "__main__":
    unittest.main()
