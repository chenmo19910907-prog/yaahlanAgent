#!/usr/bin/env python3
"""Web Agent 管理员列表操作审计日志离线验证。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from web_admin_audit_log import (  # noqa: E402
    append_admin_audit_entry,
    describe_permission_changes,
    list_admin_audit_entries,
)


class WebAdminAuditLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.audit_path = Path(self.tmp.name) / "admin_audit_log.json"

    def _patch_audit(self):
        return patch("web_admin_audit_log.AUDIT_LOG_PATH", self.audit_path)

    def test_append_and_list_entries(self) -> None:
        with self._patch_audit():
            append_admin_audit_entry(
                action="grant_admin",
                operator_staff_id="op1",
                operator_display_name="操作人",
                target_staff_id="tg1",
                target_display_name="目标用户",
            )
            payload = list_admin_audit_entries(limit=10)
            self.assertEqual(payload["total"], 1)
            entry = payload["entries"][0]
            self.assertEqual(entry["action"], "grant_admin")
            self.assertEqual(entry["actionLabel"], "设为管理员")
            self.assertEqual(entry["operatorName"], "操作人")
            self.assertEqual(entry["targetName"], "目标用户")

    def test_apply_admin_entry(self) -> None:
        with self._patch_audit():
            append_admin_audit_entry(
                action="apply_admin",
                operator_staff_id="applicant",
                operator_display_name="申请人",
                target_staff_id="applicant",
                target_display_name="申请人",
                detail="已通知超级管理员",
            )
            entry = list_admin_audit_entries(limit=1)["entries"][0]
            self.assertEqual(entry["actionLabel"], "申请管理员")

    def test_describe_permission_changes(self) -> None:
        detail = describe_permission_changes(
            before={"code_modify": False, "online": True},
            after={"code_modify": True, "online": False},
        )
        self.assertIn("开启「代码修改」", detail)
        self.assertIn("关闭「操作线上环境」", detail)


if __name__ == "__main__":
    unittest.main()
