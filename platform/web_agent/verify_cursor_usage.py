#!/usr/bin/env python3
"""cursor_usage / cursor_usage_store 单测。"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from cursor_usage import (
    CursorAuthError,
    _event_tokens,
    _fetch_admin_usage,
    _fetch_dashboard_usage,
    _normalize_session_token,
    dashboard_usage_url,
    parse_cursor_session_input,
    summarize_user_usage,
)
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
        from cursor_usage import _cache, _cache_lock

        with _cache_lock:
            _cache.clear()

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
                {"tokenUsage": {"inputTokens": 1, "outputTokens": 2}},
                {"tokenUsage": {"inputTokens": 3, "outputTokens": 4}},
            ],
        }
        with patch("cursor_usage._http_json", return_value=page1):
            stats = _fetch_dashboard_usage("token", start_ms=1, end_ms=2)
        self.assertEqual(stats["requests"], 2)
        self.assertEqual(stats["tokens"], 10)

    def test_fetch_admin_usage_aggregates(self) -> None:
        page1 = {
            "totalUsageEventsCount": 1,
            "usageEvents": [{"tokenUsage": {"inputTokens": 5, "outputTokens": 6}}],
            "pagination": {"hasNextPage": False},
        }
        with patch("cursor_usage._http_json", return_value=page1):
            stats = _fetch_admin_usage("key", email="dev@example.com", start_ms=1, end_ms=2)
        self.assertEqual(stats["requests"], 1)
        self.assertEqual(stats["tokens"], 11)

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
            store = CursorUsageCredentialStore(path=Path(tmp) / "creds.json")
            store.upsert("alice", session_token="expired-token")
            with patch("cursor_usage.get_cursor_usage_store", return_value=store):
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
            store = CursorUsageCredentialStore(path=Path(tmp) / "creds.json")
            store.upsert("alice", session_token="expired-token", cursor_email="alice@example.com")
            with patch("cursor_usage.get_cursor_usage_store", return_value=store):
                with patch("cursor_usage.load_env_local"):
                    with patch.dict(
                        "os.environ",
                        {"CURSOR_API_KEY": "cursor_test_key"},
                        clear=True,
                    ):
                        with patch(
                            "cursor_usage._fetch_dashboard_usage",
                            side_effect=CursorAuthError("会话过期"),
                        ):
                            with patch(
                                "cursor_usage._fetch_admin_usage",
                                return_value={"requests": 3, "tokens": 30},
                            ):
                                summary = summarize_user_usage("alice", range_key="month")
            self.assertEqual(summary["requests"], 3)
            self.assertEqual(summary["tokens"], 30)
            self.assertEqual(summary["source"], "cursor_admin_api")


if __name__ == "__main__":
    unittest.main()
