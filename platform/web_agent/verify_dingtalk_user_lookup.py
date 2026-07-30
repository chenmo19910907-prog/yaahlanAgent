#!/usr/bin/env python3
"""dingtalk_user_lookup 单测。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_AGENT_DIR))

import dingtalk_user_lookup as lookup  # noqa: E402
from web_session_store import SessionMeta  # noqa: E402


class DingtalkUserLookupTest(unittest.TestCase):
    def setUp(self) -> None:
        lookup._cache = None
        lookup._org_roster_cache = None

    def test_collect_all_staff_labels_merges_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lookup.WEB_AUTH_SESSIONS_PATH = root / "web_auth_sessions.json"
            lookup.MESSAGE_BOARD_PATH = root / "message_board.json"
            lookup.NAME_CACHE_PATH = root / "dingtalk_user_names.json"
            lookup.ORG_ROSTER_CACHE_PATH = root / "dingtalk_org_roster.json"

            lookup.WEB_AUTH_SESSIONS_PATH.write_text(
                json.dumps(
                    {
                        "token1": {
                            "staffId": "user_from_auth",
                            "displayName": "登录用户",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            lookup.MESSAGE_BOARD_PATH.write_text(
                json.dumps(
                    {
                        "messages": [
                            {
                                "staffId": "user_from_board",
                                "displayName": "留言用户",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            lookup.NAME_CACHE_PATH.write_text(
                json.dumps({"user_from_cache": "缓存用户"}, ensure_ascii=False),
                encoding="utf-8",
            )
            lookup.ORG_ROSTER_CACHE_PATH.write_text(
                json.dumps(
                    {
                        "fetched_at": "2026-07-30T05:00:00+00:00",
                        "users": [
                            {"staffId": "user_from_org", "displayName": "通讯录用户"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            sessions = [
                SessionMeta(
                    id="s1",
                    title="t",
                    created_at="2026-07-30T05:00:00+00:00",
                    updated_at="2026-07-30T05:00:00+00:00",
                    source="web",
                    web_owner_id="user_from_session",
                    web_owner_label="会话用户",
                    web_collaborator_ids=["user_from_collab"],
                ),
            ]

            with patch.object(lookup, "load_org_roster", return_value=[]):
                labels = lookup.collect_all_staff_labels(sessions)

            self.assertEqual(labels["user_from_auth"], "登录用户")
            self.assertEqual(labels["user_from_board"], "留言用户")
            self.assertEqual(labels["user_from_cache"], "缓存用户")
            self.assertEqual(labels["user_from_session"], "会话用户")
            self.assertIn("user_from_collab", labels)

    def test_list_selectable_staff_users_filters_query(self) -> None:
        sessions = [
            SessionMeta(
                id="s1",
                title="t",
                created_at="2026-07-30T05:00:00+00:00",
                updated_at="2026-07-30T05:00:00+00:00",
                source="web",
                web_owner_id="owner_a",
                web_owner_label="张三",
            ),
            SessionMeta(
                id="s2",
                title="t2",
                created_at="2026-07-30T05:00:00+00:00",
                updated_at="2026-07-30T05:00:00+00:00",
                source="web",
                web_owner_id="owner_b",
                web_owner_label="李四",
            ),
        ]
        with patch.object(
            lookup,
            "collect_all_staff_labels",
            return_value={"owner_a": "张三", "owner_b": "李四"},
        ):
            all_users = lookup.list_selectable_staff_users(sessions)
            filtered = lookup.list_selectable_staff_users(sessions, query="张")

        self.assertEqual(len(all_users), 2)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["displayName"], "张三")

    def test_list_selectable_staff_users_excludes_placeholder_accounts(self) -> None:
        sessions: list[SessionMeta] = []
        with patch.object(
            lookup,
            "collect_all_staff_labels",
            return_value={
                "owner_a": "张三",
                "demo": "测试员",
                "admin": "admin",
                "ghost": "",
            },
        ):
            users = lookup.list_selectable_staff_users(sessions)

        names = {user["displayName"] for user in users}
        staff_ids = {user["staffId"] for user in users}
        self.assertEqual(names, {"张三"})
        self.assertEqual(staff_ids, {"owner_a"})
        self.assertNotIn("测试员", names)
        self.assertNotIn("未知用户", names)


if __name__ == "__main__":
    unittest.main()
