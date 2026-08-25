#!/usr/bin/env python3
"""Web Agent 管理员申请流程离线验证。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
for d in (GATEWAY_DIR, WEB_AGENT_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from route_patterns import (  # noqa: E402
    is_admin_apply_decision_request,
    parse_admin_apply_decision,
)
from web_admin_apply import (  # noqa: E402
    _record_notification,
    _recently_notified,
    application_status_for_staff,
    handle_admin_apply_decision,
    submit_application,
)


class WebAdminApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.notify_path = Path(self.tmp.name) / "admin_apply_notifications.json"

    def test_route_patterns_still_parse_legacy_commands(self) -> None:
        self.assertTrue(is_admin_apply_decision_request("同意管理员申请 a1b2c3d4"))
        parsed = parse_admin_apply_decision("同意管理员申请 AbC12345")
        self.assertEqual(parsed, ("abc12345", True))

    def test_handle_admin_apply_decision_points_to_backend(self) -> None:
        msg = handle_admin_apply_decision(
            text="同意管理员申请 deadbeef",
            sender_staff_id="32274159141215328",
        )
        self.assertIn("后台手动添加", msg)

    @patch("web_admin_apply._notify_super_admins")
    @patch("web_admin_apply._gateway_import")
    def test_submit_notifies_super_admins(
        self,
        mock_gateway: unittest.mock.MagicMock,
        mock_notify: unittest.mock.MagicMock,
    ) -> None:
        mock_gateway.return_value = lambda *, sender_staff_id, sender_id: False
        result, err = submit_application(
            staff_id="user_new_001",
            display_name="测试用户",
            path=self.notify_path,
        )
        self.assertIsNone(err)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result["notified"])
        mock_notify.assert_called_once()
        status = application_status_for_staff("user_new_001", path=self.notify_path)
        self.assertEqual(status["status"], "none")

    @patch("web_admin_apply._notify_super_admins")
    @patch("web_admin_apply._gateway_import")
    def test_submit_dedup_within_24h(
        self,
        mock_gateway: unittest.mock.MagicMock,
        mock_notify: unittest.mock.MagicMock,
    ) -> None:
        mock_gateway.return_value = lambda *, sender_staff_id, sender_id: False
        _record_notification("user_new_001", path=self.notify_path)
        self.assertTrue(_recently_notified("user_new_001", path=self.notify_path))

        result, err = submit_application(
            staff_id="user_new_001",
            display_name="测试用户",
            path=self.notify_path,
        )
        self.assertIsNone(err)
        assert result is not None
        self.assertTrue(result["skippedDuplicate"])
        mock_notify.assert_not_called()

    @patch("web_admin_apply._gateway_import")
    def test_already_admin_cannot_apply(self, mock_gateway: unittest.mock.MagicMock) -> None:
        mock_gateway.return_value = lambda *, sender_staff_id, sender_id: sender_staff_id == "admin_x"
        result, err = submit_application(
            staff_id="admin_x",
            display_name="已有管理",
            path=self.notify_path,
        )
        self.assertIsNone(result)
        self.assertIn("已是管理员", err or "")


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(WebAdminApplyTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("[PASS] verify_web_admin_apply")


if __name__ == "__main__":
    main()
