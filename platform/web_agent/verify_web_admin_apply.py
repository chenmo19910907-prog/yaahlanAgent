#!/usr/bin/env python3
"""Web Agent 管理员申请流程离线验证。"""

from __future__ import annotations

import json
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
    _build_apply_card_body,
    _dtmd_robot_message,
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

    def test_apply_card_body_and_dtmd(self) -> None:
        app = {
            "token": "deadbeef",
            "staffId": "user_x",
            "displayName": "测试",
            "requestedPermissions": ["code_modify", "online"],
        }
        body = _build_apply_card_body(app)
        self.assertIn("deadbeef", body)
        self.assertIn("代码修改", body)
        self.assertIn("线上", body)
        self.assertIn("同意开放", body)
        self.assertNotIn("选权限", body)
        dtmd = _dtmd_robot_message("同意管理员申请 deadbeef")
        self.assertTrue(dtmd.startswith("dtmd://dingtalkclient/sendMessage?content="))
        self.assertIn("deadbeef", dtmd)

    @patch("web_admin_apply.resolve_application")
    def test_handle_admin_apply_decision_approves(
        self, mock_resolve: unittest.mock.MagicMock
    ) -> None:
        mock_resolve.return_value = (
            {"staffId": "user_x", "displayName": "测试"},
            None,
        )
        msg = handle_admin_apply_decision(
            text="同意管理员申请 deadbeef",
            sender_staff_id="32274159141215328",
        )
        self.assertIn("已同意", msg)
        mock_resolve.assert_called_once()

    @patch("web_admin_apply.append_admin_audit_entry")
    @patch("web_admin_apply._notify_super_admins")
    @patch("web_admin_apply._gateway_import")
    def test_submit_notifies_super_admins(
        self,
        mock_gateway: unittest.mock.MagicMock,
        mock_notify: unittest.mock.MagicMock,
        mock_audit: unittest.mock.MagicMock,
    ) -> None:
        mock_gateway.return_value = lambda *, sender_staff_id, sender_id: False
        apps_path = Path(self.tmp.name) / "admin_applications.json"
        result, err = submit_application(
            staff_id="user_new_001",
            display_name="测试用户",
            requested_permissions=["source_file"],
            path=self.notify_path,
            applications_path=apps_path,
        )
        self.assertIsNone(err)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result["notified"])
        self.assertTrue(result.get("token"))
        mock_notify.assert_called_once()
        mock_audit.assert_called_once()
        self.assertEqual(mock_audit.call_args.kwargs["action"], "apply_admin")
        self.assertIn("申请码", mock_audit.call_args.kwargs["detail"])
        apps_path = Path(self.tmp.name) / "admin_applications.json"
        status = application_status_for_staff(
            "user_new_001",
            path=apps_path,
        )
        self.assertEqual(status["status"], "pending")
        self.assertEqual(status.get("requestedPermissions"), ["source_file"])

    @patch("web_admin_apply.append_admin_audit_entry")
    @patch("web_admin_apply._notify_super_admins")
    @patch("web_admin_apply._gateway_import")
    def test_submit_dedup_same_calendar_day(
        self,
        mock_gateway: unittest.mock.MagicMock,
        mock_notify: unittest.mock.MagicMock,
        mock_audit: unittest.mock.MagicMock,
    ) -> None:
        mock_gateway.return_value = lambda *, sender_staff_id, sender_id: False
        _record_notification("user_new_001", path=self.notify_path)
        self.assertTrue(_recently_notified("user_new_001", path=self.notify_path))

        apps_path = Path(self.tmp.name) / "admin_applications.json"
        result, err = submit_application(
            staff_id="user_new_001",
            display_name="测试用户",
            path=self.notify_path,
            applications_path=apps_path,
        )
        self.assertIsNone(err)
        assert result is not None
        self.assertTrue(result["skippedDuplicate"])
        mock_notify.assert_not_called()
        mock_audit.assert_called_once()
        self.assertEqual(mock_audit.call_args.kwargs["detail"], "本自然日内重复申请")

    @patch("web_admin_apply.append_admin_audit_entry")
    @patch("web_admin_apply._notify_super_admins")
    @patch("web_admin_apply._gateway_import")
    def test_submit_supersedes_stale_pending_and_notifies(
        self,
        mock_gateway: unittest.mock.MagicMock,
        mock_notify: unittest.mock.MagicMock,
        mock_audit: unittest.mock.MagicMock,
    ) -> None:
        mock_gateway.return_value = lambda *, sender_staff_id, sender_id: False
        apps_path = Path(self.tmp.name) / "admin_applications.json"
        apps_path.write_text(
            json.dumps(
                {
                    "applications": [
                        {
                            "token": "oldtoken1",
                            "staffId": "user_new_001",
                            "displayName": "测试",
                            "status": "pending",
                            "createdAt": "2020-01-01T00:00:00+00:00",
                            "requestedPermissions": ["code_modify"],
                        }
                    ]
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        result, err = submit_application(
            staff_id="user_new_001",
            display_name="测试用户",
            requested_permissions=["online"],
            path=self.notify_path,
            applications_path=apps_path,
        )
        self.assertIsNone(err)
        assert result is not None
        self.assertTrue(result["notified"])
        self.assertNotEqual(result.get("token"), "oldtoken1")
        mock_notify.assert_called_once()
        saved = json.loads(apps_path.read_text(encoding="utf-8"))
        apps = saved["applications"]
        old = next(x for x in apps if x["token"] == "oldtoken1")
        self.assertEqual(old["status"], "superseded")

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
