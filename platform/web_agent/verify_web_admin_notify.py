#!/usr/bin/env python3
"""Web Agent 管理员变更钉钉通知离线验证。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from web_admin_notify import (  # noqa: E402
    GRANT_ADMIN_QUIT_HINT,
    broadcast_quit_admin_hint,
    build_admin_change_message,
    notify_admin_change,
    split_permission_changes,
)


class WebAdminNotifyTests(unittest.TestCase):
    def test_split_permission_changes(self) -> None:
        gained, removed = split_permission_changes(
            before={"code_modify": False, "online": True, "source_file": False},
            after={"code_modify": True, "online": False, "source_file": False},
        )
        self.assertEqual(gained, ["代码修改"])
        self.assertEqual(removed, ["操作线上环境"])

    def test_build_grant_admin_message_includes_quit_hint(self) -> None:
        text = build_admin_change_message(
            action="grant_admin",
            operator_display_name="张三",
        )
        self.assertIn("设为 Web Agent 管理员", text)
        self.assertIn("管理员列表中主动退出管理员", text)

    def test_build_update_permissions_message(self) -> None:
        text = build_admin_change_message(
            action="update_permissions",
            operator_display_name="张三",
            gained=["代码修改"],
            removed=["操作线上环境"],
        )
        self.assertIn("权限已更新", text)
        self.assertIn("获得权限：代码修改", text)
        self.assertIn("移除权限：操作线上环境", text)
        self.assertIn("操作人：张三", text)

    @patch("web_admin_notify.send_robot_private_text")
    def test_notify_skips_localhost_admin(self, mock_send) -> None:
        with patch("web_admin_notify._can_notify_staff", return_value=False):
            ok = notify_admin_change(
                action="grant_admin",
                target_staff_id="admin",
                operator_display_name="管理员",
            )
        self.assertFalse(ok)
        mock_send.assert_not_called()

    @patch("web_admin_notify.send_robot_private_text")
    @patch(
        "web_admin_notify.list_notifiable_admin_staff_ids",
        return_value=["a1", "a2"],
    )
    def test_broadcast_quit_admin_hint(self, _mock_list, mock_send) -> None:
        result = broadcast_quit_admin_hint()
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["sent"], ["a1", "a2"])
        self.assertEqual(mock_send.call_count, 2)
        for call in mock_send.call_args_list:
            self.assertEqual(call.args[1], GRANT_ADMIN_QUIT_HINT)

    @patch("web_admin_notify.send_robot_private_text")
    def test_notify_sends_text(self, mock_send) -> None:
        mock_send.return_value = None
        with patch("web_admin_notify._can_notify_staff", return_value=True):
            ok = notify_admin_change(
                action="grant_admin",
                target_staff_id="0834514151639181",
                operator_display_name="管理员",
                gained=["代码修改"],
            )
        self.assertTrue(ok)
        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        self.assertEqual(args[0], "0834514151639181")
        self.assertIn("设为 Web Agent 管理员", args[1])


if __name__ == "__main__":
    unittest.main()
