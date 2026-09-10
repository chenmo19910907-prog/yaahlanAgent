#!/usr/bin/env python3
"""admin_permission：钉钉与 Web 共用细粒度权限单测。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

GATEWAY_DIR = Path(__file__).resolve().parent
WEB_AGENT_DIR = GATEWAY_DIR.parent / "web_agent"
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(WEB_AGENT_DIR))

from admin_permission import has_admin_permission, is_admin  # noqa: E402


class AdminPermissionSharedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.grants_path = Path(self.tmp.name) / "admin_grants.json"
        self.base_allowlist = Path(self.tmp.name) / "code_modify_allowlist.json"
        self.local_allowlist = Path(self.tmp.name) / "code_modify_allowlist.local.json"
        self.base_allowlist.write_text(
            json.dumps({"allowedStaffIds": ["u1", "u2"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        self.local_allowlist.write_text("{}", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _patches(self):
        return (
            patch("code_modify_permission.ALLOWLIST_PATH", self.base_allowlist),
            patch("code_modify_permission.ALLOWLIST_LOCAL_PATH", self.local_allowlist),
            patch("web_admin_grants.GRANTS_PATH", self.grants_path),
        )

    def test_whitelist_without_grants_keeps_legacy_full_permissions(self) -> None:
        p1, p2, p3 = self._patches()
        with p1, p2, p3:
            from code_modify_permission import reload_code_modify_allowlist
            from web_admin_grants import reload_admin_grants

            reload_code_modify_allowlist()
            reload_admin_grants()
            self.assertTrue(is_admin(staff_id="u1"))
            self.assertTrue(
                has_admin_permission(staff_id="u1", permission="code_modify")
            )
            self.assertTrue(
                has_admin_permission(staff_id="u1", permission="source_file")
            )

    def test_grants_restrict_code_modify_for_dingtalk(self) -> None:
        p1, p2, p3 = self._patches()
        with p1, p2, p3:
            from code_modify_permission import reload_code_modify_allowlist
            from web_admin_grants import reload_admin_grants

            self.grants_path.write_text(
                json.dumps({"u1": ["online"]}, ensure_ascii=False),
                encoding="utf-8",
            )
            reload_code_modify_allowlist()
            reload_admin_grants()
            self.assertFalse(
                has_admin_permission(staff_id="u1", permission="code_modify")
            )
            self.assertFalse(
                has_admin_permission(staff_id="u1", permission="source_file")
            )
            self.assertTrue(
                has_admin_permission(staff_id="u1", permission="online")
            )

    def test_non_admin_denied(self) -> None:
        p1, p2, p3 = self._patches()
        with p1, p2, p3:
            from code_modify_permission import reload_code_modify_allowlist
            from web_admin_grants import reload_admin_grants

            reload_code_modify_allowlist()
            reload_admin_grants()
            self.assertFalse(is_admin(staff_id="guest"))
            self.assertFalse(
                has_admin_permission(staff_id="guest", permission="code_modify")
            )


if __name__ == "__main__":
    unittest.main()
