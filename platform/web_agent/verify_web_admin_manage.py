#!/usr/bin/env python3
"""Web Agent 管理员列表：查看与授权权限离线验证。"""

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
    ALLOWLIST_PATH,
    load_code_modify_allowlist,
)
from web_admin_manage import (  # noqa: E402
    CHENMO_STAFF_ID,
    can_manage_admin_roles,
    can_quit_admin_role,
    is_protected_admin_account,
    list_admin_users,
    quit_admin_role,
    remove_admin_list_user,
    reload_admin_list_hidden_staff_ids,
    set_admin_permissions,
    set_admin_role,
)
from web_admin_grants import is_super_admin, reload_admin_grants  # noqa: E402


class WebAdminManageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base_allowlist = Path(self.tmp.name) / "code_modify_allowlist.json"
        self.local_allowlist = Path(self.tmp.name) / "code_modify_allowlist.local.json"
        self.grants_path = Path(self.tmp.name) / "admin_grants.json"
        self.hidden_path = Path(self.tmp.name) / "admin_list_hidden.json"
        self.hidden_path.write_text("[]\n", encoding="utf-8")
        self.base_allowlist.write_text(
            json.dumps({"allowedStaffIds": [CHENMO_STAFF_ID]}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self.local_allowlist.write_text(
            json.dumps({"allowedStaffIds": []}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _patch_allowlist(self):
        return patch.multiple(
            "code_modify_permission",
            ALLOWLIST_PATH=self.base_allowlist,
            ALLOWLIST_LOCAL_PATH=self.local_allowlist,
        )

    def _patch_grants(self):
        return patch("web_admin_grants.GRANTS_PATH", self.grants_path)

    def _patch_hidden(self):
        return patch("web_admin_manage.HIDDEN_USERS_PATH", self.hidden_path)

    def test_can_manage_only_admin_and_chenmo(self) -> None:
        with self._patch_grants():
            reload_admin_grants()
            self.assertTrue(can_manage_admin_roles(staff_id="admin"))
            self.assertTrue(can_manage_admin_roles(staff_id=CHENMO_STAFF_ID))
            self.assertTrue(can_manage_admin_roles(staff_id="x", display_name="陈墨"))
            self.assertFalse(can_manage_admin_roles(staff_id="0834514151639181"))
            self.assertFalse(can_manage_admin_roles(staff_id="other-user"))

    def test_protected_accounts(self) -> None:
        self.assertTrue(is_protected_admin_account("admin"))
        self.assertTrue(is_protected_admin_account(CHENMO_STAFF_ID))
        self.assertFalse(is_protected_admin_account("0834514151639181"))

    def test_can_manage_includes_super_admin(self) -> None:
        target = "0834514151639181"
        with self._patch_allowlist(), self._patch_grants():
            load_code_modify_allowlist.cache_clear()
            reload_admin_grants()
            self.grants_path.write_text(
                json.dumps({target: ["super_admin"]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            reload_admin_grants()
            self.assertTrue(can_manage_admin_roles(staff_id=target))
            self.assertTrue(is_super_admin(target))

    def test_grant_and_revoke_by_admin(self) -> None:
        target = "0834514151639181"
        with self._patch_allowlist(), self._patch_grants():
            load_code_modify_allowlist.cache_clear()
            reload_admin_grants()
            result, err = set_admin_role(
                operator_staff_id="admin",
                operator_display_name="管理员",
                target_staff_id=target,
                is_admin=True,
            )
            self.assertIsNone(err)
            assert result is not None
            self.assertTrue(result["isAdmin"])
            cfg = load_code_modify_allowlist()
            self.assertIn(target, cfg.allowed_staff_ids)

            result2, err2 = set_admin_role(
                operator_staff_id="admin",
                operator_display_name="管理员",
                target_staff_id=target,
                is_admin=False,
            )
            self.assertIsNone(err2)
            assert result2 is not None
            self.assertFalse(result2["isAdmin"])
            cfg2 = load_code_modify_allowlist()
            self.assertNotIn(target, cfg2.allowed_staff_ids)
            self.assertNotIn(target, reload_admin_grants())

    def test_set_super_admin_permissions(self) -> None:
        target = "0834514151639181"
        with self._patch_allowlist(), self._patch_grants():
            load_code_modify_allowlist.cache_clear()
            reload_admin_grants()
            set_admin_role(
                operator_staff_id="admin",
                operator_display_name="管理员",
                target_staff_id=target,
                is_admin=True,
            )
            result, err = set_admin_permissions(
                operator_staff_id="admin",
                operator_display_name="管理员",
                target_staff_id=target,
                permissions={
                    "super_admin": True,
                    "code_modify": False,
                    "source_file": False,
                    "online": False,
                },
            )
            self.assertIsNone(err)
            assert result is not None
            self.assertTrue(result["permissions"]["super_admin"])
            self.assertTrue(result["permissions"]["code_modify"])
            self.assertTrue(result["permissions"]["online"])
            grants = reload_admin_grants()
            self.assertEqual(grants.get(target), ["super_admin"])

    def test_set_permissions_for_admin(self) -> None:
        target = "0834514151639181"
        with self._patch_allowlist(), self._patch_grants():
            load_code_modify_allowlist.cache_clear()
            reload_admin_grants()
            set_admin_role(
                operator_staff_id="admin",
                operator_display_name="管理员",
                target_staff_id=target,
                is_admin=True,
            )
            result, err = set_admin_permissions(
                operator_staff_id="admin",
                operator_display_name="管理员",
                target_staff_id=target,
                permissions={
                    "super_admin": False,
                    "code_modify": True,
                    "source_file": False,
                    "online": True,
                },
            )
            self.assertIsNone(err)
            assert result is not None
            self.assertTrue(result["permissions"]["code_modify"])
            self.assertFalse(result["permissions"]["source_file"])
            self.assertTrue(result["permissions"]["online"])
            grants = reload_admin_grants()
            self.assertEqual(grants.get(target), ["code_modify", "online"])

    def test_viewer_cannot_modify(self) -> None:
        with self._patch_allowlist(), self._patch_grants():
            load_code_modify_allowlist.cache_clear()
            reload_admin_grants()
            _, err = set_admin_role(
                operator_staff_id="0834514151639181",
                operator_display_name="测试员",
                target_staff_id="999",
                is_admin=True,
            )
            self.assertEqual(err, "没有权限")

    def test_cannot_revoke_chenmo(self) -> None:
        with self._patch_allowlist(), self._patch_grants():
            load_code_modify_allowlist.cache_clear()
            _, err = set_admin_role(
                operator_staff_id="admin",
                operator_display_name="管理员",
                target_staff_id=CHENMO_STAFF_ID,
                is_admin=False,
            )
            self.assertEqual(err, "该账号不可撤销管理员")

    def test_list_excludes_placeholder_accounts(self) -> None:
        with self._patch_allowlist(), self._patch_grants(), self._patch_hidden():
            load_code_modify_allowlist.cache_clear()
            reload_admin_grants()
            reload_admin_list_hidden_staff_ids()
            with patch(
                "dingtalk_user_lookup.collect_cached_staff_labels",
                return_value={
                    "owner_a": "张三",
                    "demo": "测试员",
                    "ghost": "未知用户",
                },
            ), patch(
                "web_session_store.get_session_store",
            ) as mock_store:
                mock_store.return_value.list_sessions.return_value = []
                payload = list_admin_users(
                    viewer_staff_id="admin",
                    viewer_display_name="管理员",
                )
        names = {user["displayName"] for user in payload["users"]}
        staff_ids = {user["staffId"] for user in payload["users"]}
        self.assertEqual(names, {"张三"})
        self.assertEqual(staff_ids, {"owner_a"})

    def test_list_sorts_super_admin_and_admin_first(self) -> None:
        target = "0834514151639181"
        regular_admin = "regular-admin-id"
        with self._patch_allowlist(), self._patch_grants(), self._patch_hidden():
            load_code_modify_allowlist.cache_clear()
            reload_admin_grants()
            reload_admin_list_hidden_staff_ids()
            self.local_allowlist.write_text(
                json.dumps({"allowedStaffIds": [regular_admin]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            load_code_modify_allowlist.cache_clear()
            self.grants_path.write_text(
                json.dumps({target: ["super_admin"]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            reload_admin_grants()
            with patch(
                "dingtalk_user_lookup.collect_cached_staff_labels",
                return_value={
                    "alice": "Alice",
                    target: "Bob",
                    regular_admin: "Carol",
                },
            ), patch(
                "web_session_store.get_session_store",
            ) as mock_store:
                mock_store.return_value.list_sessions.return_value = []
                payload = list_admin_users(
                    viewer_staff_id="admin",
                    viewer_display_name="管理员",
                )
        ordered = [(u["displayName"], u.get("isSuperAdmin"), u.get("isAdmin")) for u in payload["users"]]
        self.assertEqual(
            ordered,
            [
                ("Bob", True, False),
                ("Carol", False, True),
                ("Alice", False, False),
            ],
        )

    def test_list_sorts_builtin_super_admin_before_other_super_admin(self) -> None:
        target = "0834514151639181"
        with self._patch_allowlist(), self._patch_grants(), self._patch_hidden():
            load_code_modify_allowlist.cache_clear()
            reload_admin_grants()
            reload_admin_list_hidden_staff_ids()
            self.grants_path.write_text(
                json.dumps({target: ["super_admin"]}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            reload_admin_grants()
            with patch(
                "dingtalk_user_lookup.collect_cached_staff_labels",
                return_value={
                    "admin": "管理员",
                    CHENMO_STAFF_ID: "陈墨",
                    target: "丁亮",
                    "alice": "Alice",
                },
            ), patch(
                "web_session_store.get_session_store",
            ) as mock_store:
                mock_store.return_value.list_sessions.return_value = []
                payload = list_admin_users(
                    viewer_staff_id="admin",
                    viewer_display_name="管理员",
                )
        ordered = [u["displayName"] for u in payload["users"]]
        staff_ids = {u["staffId"] for u in payload["users"]}
        self.assertNotIn("admin", staff_ids)
        self.assertEqual(ordered[:2], ["陈墨", "丁亮"])

    def test_list_excludes_localhost_admin(self) -> None:
        with self._patch_allowlist(), self._patch_grants(), self._patch_hidden():
            load_code_modify_allowlist.cache_clear()
            reload_admin_grants()
            reload_admin_list_hidden_staff_ids()
            with patch(
                "dingtalk_user_lookup.collect_cached_staff_labels",
                return_value={
                    "admin": "管理员",
                    "alice": "Alice",
                },
            ), patch(
                "web_session_store.get_session_store",
            ) as mock_store:
                mock_store.return_value.list_sessions.return_value = []
                payload = list_admin_users(
                    viewer_staff_id="admin",
                    viewer_display_name="管理员",
                )
        staff_ids = {user["staffId"] for user in payload["users"]}
        self.assertNotIn("admin", staff_ids)
        self.assertEqual({user["displayName"] for user in payload["users"]}, {"Alice"})

    def test_remove_ordinary_user(self) -> None:
        target = "0834514151639181"
        with self._patch_allowlist(), self._patch_grants(), self._patch_hidden():
            load_code_modify_allowlist.cache_clear()
            reload_admin_grants()
            reload_admin_list_hidden_staff_ids()
            result, err = remove_admin_list_user(
                operator_staff_id="admin",
                operator_display_name="管理员",
                target_staff_id=target,
            )
            self.assertIsNone(err)
            assert result is not None
            self.assertTrue(result["removed"])
            hidden = reload_admin_list_hidden_staff_ids()
            self.assertIn(target, hidden)

    def test_quit_admin_role(self) -> None:
        target = "0834514151639181"
        with self._patch_allowlist(), self._patch_grants():
            load_code_modify_allowlist.cache_clear()
            reload_admin_grants()
            set_admin_role(
                operator_staff_id="admin",
                operator_display_name="管理员",
                target_staff_id=target,
                is_admin=True,
            )
            self.assertTrue(can_quit_admin_role(target))
            result, err = quit_admin_role(staff_id=target)
            self.assertIsNone(err)
            assert result is not None
            self.assertFalse(result["isAdmin"])
            self.assertFalse(can_quit_admin_role(target))

    def test_protected_cannot_quit(self) -> None:
        with self._patch_allowlist(), self._patch_grants():
            load_code_modify_allowlist.cache_clear()
            reload_admin_grants()
            self.assertFalse(can_quit_admin_role(CHENMO_STAFF_ID))
            _, err = quit_admin_role(staff_id=CHENMO_STAFF_ID)
            self.assertEqual(err, "该账号不可退出管理员")


if __name__ == "__main__":
    unittest.main()
