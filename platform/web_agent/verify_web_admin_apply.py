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

from code_modify_permission import (  # noqa: E402
    ALLOWLIST_LOCAL_PATH,
    load_code_modify_allowlist,
)
from route_patterns import (  # noqa: E402
    is_admin_apply_decision_request,
    parse_admin_apply_decision,
)
from web_admin_apply import (  # noqa: E402
    application_status_for_staff,
    resolve_application,
    submit_application,
)


class WebAdminApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.apps_path = Path(self.tmp.name) / "admin_applications.json"
        self.local_allowlist = Path(self.tmp.name) / "code_modify_allowlist.local.json"

    def test_route_patterns(self) -> None:
        self.assertTrue(is_admin_apply_decision_request("同意管理员申请 a1b2c3d4"))
        self.assertTrue(is_admin_apply_decision_request("拒绝管理员申请 a1b2c3d4"))
        self.assertFalse(is_admin_apply_decision_request("同意管理员 a1b2c3d4"))
        parsed = parse_admin_apply_decision("同意管理员申请 AbC12345")
        self.assertEqual(parsed, ("abc12345", True))

    @patch("web_admin_apply._notify_admin")
    @patch("web_admin_apply._gateway_import")
    def test_submit_and_approve(
        self,
        mock_gateway: unittest.mock.MagicMock,
        mock_notify: unittest.mock.MagicMock,
    ) -> None:
        mock_notify.return_value = None

        def fake_add(staff_id: str) -> bool:
            data = {"allowedStaffIds": [staff_id]}
            self.local_allowlist.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return True

        mock_gateway.return_value = (
            fake_add,
            lambda: ["32274159141215328"],
            lambda *, sender_staff_id, sender_id: sender_staff_id
            in {"32274159141215328"},
        )

        app, err = submit_application(
            staff_id="user_new_001",
            display_name="测试用户",
            path=self.apps_path,
        )
        self.assertIsNone(err)
        self.assertIsNotNone(app)
        assert app is not None
        self.assertEqual(app["status"], "pending")
        mock_notify.assert_called_once()

        status = application_status_for_staff("user_new_001", path=self.apps_path)
        self.assertEqual(status["status"], "pending")

        with patch(
            "code_modify_permission.ALLOWLIST_LOCAL_PATH",
            self.local_allowlist,
        ):
            load_code_modify_allowlist.cache_clear()
            with patch("web_admin_apply._notify_applicant"):
                with patch("web_admin_apply._gateway_import") as mock_gateway2:
                    mock_gateway2.return_value = (
                        fake_add,
                        lambda: ["32274159141215328"],
                        lambda *, sender_staff_id, sender_id: sender_staff_id
                        in {"32274159141215328"},
                    )
                    approved, err2 = resolve_application(
                        token=app["token"],
                        approver_staff_id="32274159141215328",
                        approve=True,
                        path=self.apps_path,
                    )
            self.assertIsNone(err2)
            self.assertEqual(approved["status"], "approved")
            local = json.loads(self.local_allowlist.read_text(encoding="utf-8"))
            self.assertIn("user_new_001", local["allowedStaffIds"])

    @patch("web_admin_apply._gateway_import")
    def test_non_admin_cannot_approve(self, mock_gateway: unittest.mock.MagicMock) -> None:
        mock_gateway.return_value = (
            lambda _sid: False,
            lambda: ["32274159141215328"],
            lambda *, sender_staff_id, sender_id: False,
        )
        self.apps_path.write_text(
            json.dumps(
                {
                    "applications": [
                        {
                            "token": "deadbeef",
                            "staffId": "user_x",
                            "displayName": "X",
                            "status": "pending",
                            "createdAt": "2026-08-05T00:00:00+00:00",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        app, err = resolve_application(
            token="deadbeef",
            approver_staff_id="999",
            approve=True,
            path=self.apps_path,
        )
        self.assertIsNone(app)
        self.assertIn("权限", err or "")


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(WebAdminApplyTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("[PASS] verify_web_admin_apply")


if __name__ == "__main__":
    main()
