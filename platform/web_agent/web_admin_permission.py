"""网页版 Agent：管理员权限（会话清空等高危操作）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_gateway = Path(__file__).resolve().parents[1] / "dingtalk_gateway"
if str(_gateway) not in sys.path:
    sys.path.insert(0, str(_gateway))

from code_modify_permission import is_code_modify_allowed
from env_loader import load_env_local
from web_admin_grants import get_admin_permission_map, permission_definitions

DENY_MESSAGE = "没有权限"


def _localhost_admin_staff_id() -> str:
    load_env_local()
    return os.environ.get("WEB_AGENT_LOCAL_ADMIN_STAFF_ID", "admin").strip() or "admin"


def is_protected_web_admin(staff_id: str | None) -> bool:
    uid = (staff_id or "").strip()
    if not uid:
        return False
    if uid == _localhost_admin_staff_id():
        return True
    return uid == "32274159141215328"


def is_web_admin(*, staff_id: str | None) -> bool:
    """是否网页版管理员（与网关代码修改白名单共用 staffId 列表）。"""
    uid = (staff_id or "").strip()
    if not uid:
        return False
    if uid == _localhost_admin_staff_id():
        return True
    return is_code_modify_allowed(sender_staff_id=uid, sender_id=None)


def has_admin_permission(*, staff_id: str | None, permission: str) -> bool:
    """管理员是否拥有某项细粒度权限；非管理员恒为 False。"""
    uid = (staff_id or "").strip()
    key = (permission or "").strip()
    if not uid or not key:
        return False
    admin = is_web_admin(staff_id=uid)
    perm_map = get_admin_permission_map(
        staff_id=uid,
        is_admin=admin,
        protected=is_protected_web_admin(uid),
    )
    return bool(perm_map.get(key))


def list_admin_permission_definitions() -> list[dict[str, str]]:
    return permission_definitions()


def web_admin_denial_message() -> str:
    return DENY_MESSAGE
