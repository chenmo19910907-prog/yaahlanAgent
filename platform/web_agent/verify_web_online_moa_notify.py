#!/usr/bin/env python3
"""线上 MOA 超管钉钉通知离线验证。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from web_online_moa_notify import (  # noqa: E402
    build_online_moa_alert_message,
    notify_super_admins_online_moa,
)


class WebOnlineMoaNotifyTests(unittest.TestCase):
    def test_build_message(self) -> None:
        text = build_online_moa_alert_message(
            {
                "operation": "用户 100 发放 10 钻石",
                "operatorName": "测试员",
                "accountSummary": "100",
                "moaInterface": "/service/foo · bar",
                "paramsSummary": "num=10",
                "resultSummary": "成功",
                "environment": "online",
                "source": "moa",
            }
        )
        self.assertIn("线上 MOA", text)
        self.assertIn("测试员", text)
        self.assertIn("发放 10 钻石", text)

    @patch("web_admin_notify.send_robot_private_text")
    @patch("web_admin_grants.list_super_admin_staff_ids", return_value=["admin1", "admin2"])
    @patch("web_admin_notify._can_notify_staff", return_value=True)
    def test_notify_skips_operator(self, _can, _list, mock_send) -> None:
        sent = notify_super_admins_online_moa(
            {
                "source": "moa",
                "environment": "online",
                "operation": "查询 userId",
                "operatorName": "甲",
            },
            operator_staff_id="admin1",
        )
        self.assertEqual(sent, 1)
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args[0][0], "admin2")

    @patch("web_admin_notify.send_robot_private_text")
    def test_test_env_no_notify(self, mock_send) -> None:
        sent = notify_super_admins_online_moa(
            {"source": "moa", "environment": "test", "operation": "x"},
        )
        self.assertEqual(sent, 0)
        mock_send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
