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

    def test_prefer_staff_label_prefers_chinese(self) -> None:
        self.assertEqual(lookup._prefer_staff_label("Kaibo", "王凯波"), "王凯波")
        self.assertEqual(lookup._prefer_staff_label("王凯波", "Kaibo"), "王凯波")

    def test_resolve_staff_display_name_uses_known_labels(self) -> None:
        name = lookup.resolve_staff_display_name(
            "uid_kaibo",
            known_labels={"uid_kaibo": "王凯波"},
            fallback_label="Kaibo",
        )
        self.assertEqual(name, "王凯波")

    def test_enrich_session_owner_labels_upgrades_english_nickname(self) -> None:
        sessions = [
            SessionMeta(
                id="s1",
                title="t",
                created_at="2026-07-30T05:00:00+00:00",
                updated_at="2026-07-30T05:00:00+00:00",
                source="dingtalk",
                dingtalk_key="cid:user:uid_kaibo",
                dingtalk_label="Kaibo",
                dingtalk_owner_id="uid_kaibo",
            ),
        ]
        with patch.object(
            lookup,
            "collect_all_staff_labels",
            return_value={"uid_kaibo": "王凯波"},
        ):
            updated = lookup.enrich_session_owner_labels(sessions, try_api=False)
        self.assertEqual(updated, 1)
        self.assertEqual(sessions[0].dingtalk_label, "王凯波")

    def test_resolve_dingtalk_name_prefers_api_chinese_over_known_pinyin(self) -> None:
        uid = "uid_xueming"
        with patch.object(lookup, "_fetch_name_from_api", return_value="程学明"):
            lookup._cache = {}
            name = lookup.resolve_dingtalk_name(
                uid,
                known={uid: "Xueming"},
                try_api=True,
            )
        self.assertEqual(name, "程学明")

    def test_collect_all_staff_labels_upgrades_ascii_via_api(self) -> None:
        sessions = [
            SessionMeta(
                id="s1",
                title="t",
                created_at="2026-07-30T05:00:00+00:00",
                updated_at="2026-07-30T05:00:00+00:00",
                source="web",
                web_owner_id="uid_xueming",
                web_owner_label="Xueming",
            ),
        ]
        with patch.object(lookup, "collect_web_auth_staff_labels", return_value={}):
            with patch.object(lookup, "collect_message_board_staff_labels", return_value={}):
                with patch.object(lookup, "load_org_roster", return_value=[]):
                    with patch.object(lookup, "_load_cache", return_value={}):
                        with patch.object(
                            lookup,
                            "resolve_dingtalk_name",
                            return_value="程学明",
                        ) as resolve_mock:
                            labels = lookup.collect_all_staff_labels(
                                sessions,
                                max_api_lookups=12,
                            )
        resolve_mock.assert_called_once()
        self.assertEqual(labels["uid_xueming"], "程学明")

    def test_chinese_display_name_strips_english_suffix(self) -> None:
        self.assertEqual(lookup.chinese_display_name("丁亮 Liang"), "丁亮")
        self.assertEqual(lookup.chinese_display_name("韩敏-HanMin"), "韩敏")
        self.assertEqual(lookup.chinese_display_name("曲博-qubo"), "曲博")
        self.assertEqual(lookup.chinese_display_name("陈墨"), "陈墨")
        self.assertEqual(lookup.chinese_display_name("Kaibo"), "Kaibo")
        self.assertEqual(lookup.chinese_display_name(""), "")

    def test_public_display_name_uses_chinese_only(self) -> None:
        self.assertEqual(
            lookup._public_display_name("丁亮 Liang", "0834514151639181"),
            "丁亮",
        )

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

    def test_list_selectable_group_chats(self) -> None:
        sessions = [
            SessionMeta(
                id="s1",
                title="t",
                created_at="2026-07-30T05:00:00+00:00",
                updated_at="2026-07-30T05:00:00+00:00",
                source="dingtalk",
                dingtalk_key="cidGroupA==:user:uid_a",
            ),
        ]
        with patch.object(
            lookup,
            "_collect_candidate_group_ids",
            return_value=["cidGroupA==", "cidGroupB==", "cidGroupC=="],
        ), patch.object(
            lookup,
            "_load_group_chat_index",
            return_value={
                "cidGroupB==": {"conversationTitle": "测试群 Yaahlan"},
                "cidGroupA==": {"conversationTitle": "A 群"},
            },
        ):
            groups = lookup.list_selectable_group_chats(sessions)
        ids = {item["conversationId"] for item in groups}
        self.assertIn("cidGroupA==", ids)
        self.assertIn("cidGroupB==", ids)
        self.assertNotIn("cidGroupC==", ids)
        titles = {item["conversationId"]: item["displayName"] for item in groups}
        self.assertEqual(titles["cidGroupB=="], "测试群 Yaahlan")

    def test_is_named_group_title(self) -> None:
        self.assertTrue(lookup.is_named_group_title("测试群"))
        self.assertFalse(lookup.is_named_group_title(""))
        self.assertFalse(lookup.is_named_group_title("钉钉群"))
        self.assertFalse(lookup.is_named_group_title("钉钉群 · cidABC"))

    def test_parse_dingtalk_open_conversation_id(self) -> None:
        self.assertEqual(
            lookup.parse_dingtalk_open_conversation_id("cidABC==:user:123"),
            "cidABC==",
        )
        self.assertEqual(lookup.parse_dingtalk_open_conversation_id("dm:123"), "")

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
