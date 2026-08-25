#!/usr/bin/env python3
"""web_admin_grants / has_admin_permission 单测。"""

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

from web_admin_grants import (  # noqa: E402
    GRANULAR_PERMISSION_KEYS,
    get_admin_permission_map,
    is_super_admin,
    list_super_admin_staff_ids,
    reload_admin_grants,
    save_admin_permissions,
)
from web_admin_permission import has_admin_permission, is_web_admin  # noqa: E402


class WebAdminGrantsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.grants_path = Path(self.tmp.name) / "admin_grants.json"

    def _patch_grants(self):
        return patch("web_admin_grants.GRANTS_PATH", self.grants_path)

    def test_new_admin_starts_without_permissions(self) -> None:
        staff_id = "0834514151639181"
        with self._patch_grants():
            reload_admin_grants()
            save_admin_permissions(
                staff_id=staff_id,
                permissions={
                    "super_admin": False,
                    "code_modify": False,
                    "source_file": False,
                    "online": False,
                },
            )
            perm_map = get_admin_permission_map(
                staff_id=staff_id,
                is_admin=True,
                protected=False,
            )
            self.assertFalse(any(perm_map.values()))

    def test_legacy_admin_has_all_granular_permissions(self) -> None:
        staff_id = "0834514151639181"
        with self._patch_grants():
            reload_admin_grants()
            perm_map = get_admin_permission_map(
                staff_id=staff_id,
                is_admin=True,
                protected=False,
            )
            self.assertFalse(perm_map["super_admin"])
            for key in GRANULAR_PERMISSION_KEYS:
                self.assertTrue(perm_map[key])

    def test_super_admin_grants_all_permissions(self) -> None:
        staff_id = "0834514151639181"
        with self._patch_grants():
            reload_admin_grants()
            save_admin_permissions(
                staff_id=staff_id,
                permissions={"super_admin": True},
            )
            perm_map = get_admin_permission_map(
                staff_id=staff_id,
                is_admin=True,
                protected=False,
            )
            self.assertTrue(all(perm_map.values()))
            self.assertTrue(is_super_admin(staff_id))

    def test_has_admin_permission_respects_grants(self) -> None:
        staff_id = "0834514151639181"
        with patch("web_admin_permission.is_web_admin", return_value=True), patch(
            "web_admin_permission.is_protected_web_admin",
            return_value=False,
        ), self._patch_grants():
            reload_admin_grants()
            self.grants_path.write_text(
                json.dumps({staff_id: ["online"]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            reload_admin_grants()
            self.assertFalse(has_admin_permission(staff_id=staff_id, permission="code_modify"))
            self.assertTrue(has_admin_permission(staff_id=staff_id, permission="online"))

    def test_non_admin_has_no_permission(self) -> None:
        with patch("web_admin_permission.is_web_admin", return_value=False):
            self.assertFalse(has_admin_permission(staff_id="x", permission="online"))

    def test_protected_admin_is_super_admin(self) -> None:
        with self._patch_grants():
            reload_admin_grants()
            for staff_id in ("admin", "32274159141215328"):
                perm_map = get_admin_permission_map(
                    staff_id=staff_id,
                    is_admin=True,
                    protected=True,
                )
                self.assertTrue(all(perm_map.values()))
                self.assertTrue(is_super_admin(staff_id))

    def test_list_super_admin_staff_ids(self) -> None:
        with self._patch_grants():
            reload_admin_grants()
            save_admin_permissions(
                staff_id="user_sa",
                permissions={"super_admin": True},
            )
            ids = list_super_admin_staff_ids()
            self.assertIn("32274159141215328", ids)
            self.assertIn("user_sa", ids)


if __name__ == "__main__":
    unittest.main()
