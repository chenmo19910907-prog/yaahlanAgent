#!/usr/bin/env python3
"""超管用户资料卡与钉钉私聊离线验证。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

if "requests" not in sys.modules:
    sys.modules["requests"] = MagicMock()

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
for d in (GATEWAY_DIR, WEB_AGENT_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

import web_super_admin_user_profile as profile  # noqa: E402


class WebSuperAdminUserProfileTests(unittest.TestCase):
    @patch("web_admin_grants.is_super_admin", return_value=False)
    @patch.object(profile, "_dingtalk_user_detail_cached", return_value={"hired_date": 1597573616828, "dept_id_list": [1], "mobile": "13800000000"})
    @patch("dingtalk_user_lookup.lookup_auth_user_display_name", return_value="用户A")
    @patch("dingtalk_user_profile.resolve_user_profile")
    @patch("dingtalk_user_lookup.resolve_user_avatars", return_value={})
    def test_profile_non_super_hides_sensitive(
        self,
        _avatars: object,
        mock_profile: object,
        _lookup: object,
        _detail: object,
        _mock_super: object,
    ) -> None:
        from dingtalk_user_profile import UserProfile

        mock_profile.return_value = UserProfile(
            staff_id="u1",
            display_name="用户A",
            avatar_url="",
        )
        payload, err = profile.get_user_profile_card(
            target_staff_id="u1",
            viewer_staff_id="viewer",
        )
        self.assertIsNone(err)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertFalse(payload["canSendDingtalkMessage"])
        card_labels = {r["label"] for r in payload["cardRows"]}
        self.assertNotIn("dingtalkFields", payload)
        for hidden in ("部门 ID", "直属主管", "入职日期", "钉钉姓名"):
            self.assertNotIn(hidden, card_labels)
        for removed in ("部门", "部门负责人", "职位", "手机号"):
            self.assertNotIn(removed, card_labels)
        self.assertTrue(payload.get("cardRows"))

    @patch("web_admin_grants.is_super_admin", return_value=True)
    @patch.object(profile, "_analytics_usage_rows", return_value=[("Web 提问次数", "3 次（本月）"), ("Token 用量", "")])
    @patch.object(profile, "_dingtalk_user_detail_cached", return_value={"title": "工程师"})
    @patch("dingtalk_user_lookup.lookup_auth_user_display_name", return_value="用户A")
    @patch("dingtalk_user_profile.resolve_user_profile")
    @patch("dingtalk_user_lookup.resolve_user_avatars", return_value={})
    def test_profile_super_admin_card_rows_show_empty_slots(
        self,
        _avatars: object,
        mock_resolve: object,
        _lookup: object,
        _detail: object,
        _analytics: object,
        _mock_super: object,
    ) -> None:
        from dingtalk_user_profile import UserProfile

        mock_resolve.return_value = UserProfile(
            staff_id="u1",
            display_name="用户A",
            avatar_url="",
        )
        payload, err = profile.get_user_profile_card(
            target_staff_id="u1",
            viewer_staff_id="super",
        )
        self.assertIsNone(err)
        assert payload is not None
        rows = {r["label"]: r["value"] for r in payload["cardRows"]}
        for removed in ("部门", "部门负责人", "职位", "手机号", "钉钉姓名", "部门 ID", "直属主管"):
            self.assertNotIn(removed, rows)
        self.assertNotIn("unionid", rows)
        self.assertNotIn("Token 用量", rows)
        self.assertNotIn("受保护账号", rows)
        self.assertTrue(payload["canSendDingtalkMessage"])

    def test_format_hired_date_ms(self) -> None:
        self.assertEqual(profile._format_hired_date(1597573616828), "2020-08-16")

    def test_format_account_status(self) -> None:
        self.assertEqual(profile._format_account_status(True), "正常")
        self.assertEqual(profile._format_account_status(False), "未激活")

    @patch("web_admin_grants.is_super_admin", return_value=True)
    def test_send_empty_message(self, _mock: object) -> None:
        payload, err = profile.send_super_admin_dingtalk_message(
            operator_staff_id="op",
            operator_display_name="陈墨",
            target_staff_id="target1",
            message="  ",
        )
        self.assertIsNone(payload)
        self.assertIn("不能为空", err or "")

    @patch("web_admin_grants.is_super_admin", return_value=False)
    def test_message_log_requires_super(self, _mock: object) -> None:
        payload, err = profile.list_super_admin_dingtalk_message_log(
            viewer_staff_id="viewer",
        )
        self.assertIsNone(payload)
        self.assertIn("超级管理员", err or "")

    @patch("web_admin_grants.is_super_admin", return_value=True)
    @patch("web_super_admin_message_log.list_super_admin_message_entries")
    def test_message_log_list(self, mock_list: object, _mock: object) -> None:
        mock_list.return_value = {
            "entries": [{"sentAt": "2026-01-01T00:00:00+00:00", "message": "hi"}],
            "total": 1,
            "limit": 50,
            "offset": 0,
            "hasMore": False,
        }
        payload, err = profile.list_super_admin_dingtalk_message_log(
            viewer_staff_id="super",
            target_staff_id="u2",
        )
        self.assertIsNone(err)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["total"], 1)
        mock_list.assert_called_once_with(limit=50, offset=0, target_staff_id="u2")


if __name__ == "__main__":
    unittest.main()
