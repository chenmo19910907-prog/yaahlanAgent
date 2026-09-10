"""钉钉网关与 Web Agent 共用的管理员身份与细粒度权限校验。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from code_modify_permission import is_code_modify_allowed
from env_loader import load_env_local

_WEB_AGENT_DIR = Path(__file__).resolve().parents[1] / "web_agent"
if str(_WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_WEB_AGENT_DIR))

from web_admin_grants import get_admin_permission_map, permission_definitions  # noqa: E402

DENY_MESSAGE = "没有权限"
CHENMO_STAFF_ID = "32274159141215328"


def _localhost_admin_staff_id() -> str:
    load_env_local()
    return os.environ.get("WEB_AGENT_LOCAL_ADMIN_STAFF_ID", "admin").strip() or "admin"


def is_protected_web_admin(staff_id: str | None) -> bool:
    uid = (staff_id or "").strip()
    if not uid:
        return False
    if uid == _localhost_admin_staff_id():
        return True
    return uid == CHENMO_STAFF_ID


def resolve_admin_user_id(
    *,
    sender_staff_id: str | None = None,
    sender_id: str | None = None,
    staff_id: str | None = None,
) -> str:
    """返回用于 grants 查表的 userId（优先 staffId）。"""
    if staff_id is not None:
        return (staff_id or "").strip()
    staff = (sender_staff_id or "").strip()
    sender = (sender_id or "").strip()
    if staff and is_code_modify_allowed(sender_staff_id=staff, sender_id=None):
        return staff
    if sender and is_code_modify_allowed(sender_staff_id=None, sender_id=sender):
        return sender
    return staff or sender


def is_admin(
    *,
    sender_staff_id: str | None = None,
    sender_id: str | None = None,
    staff_id: str | None = None,
) -> bool:
    """是否管理员（与 code_modify_allowlist 共用身份列表）。"""
    uid = resolve_admin_user_id(
        sender_staff_id=sender_staff_id,
        sender_id=sender_id,
        staff_id=staff_id,
    )
    if not uid:
        return False
    if uid == _localhost_admin_staff_id():
        return True
    staff = (sender_staff_id or staff_id or "").strip()
    sender = (sender_id or "").strip()
    return is_code_modify_allowed(
        sender_staff_id=staff or None,
        sender_id=sender or None,
    )


def has_admin_permission(
    *,
    sender_staff_id: str | None = None,
    sender_id: str | None = None,
    staff_id: str | None = None,
    permission: str,
) -> bool:
    """管理员是否拥有某项细粒度权限；非管理员恒为 False。"""
    uid = resolve_admin_user_id(
        sender_staff_id=sender_staff_id,
        sender_id=sender_id,
        staff_id=staff_id,
    )
    key = (permission or "").strip()
    if not uid or not key:
        return False
    admin = is_admin(
        sender_staff_id=sender_staff_id,
        sender_id=sender_id,
        staff_id=staff_id,
    )
    perm_map = get_admin_permission_map(
        staff_id=uid,
        is_admin=admin,
        protected=is_protected_web_admin(uid),
    )
    return bool(perm_map.get(key))


def is_web_admin(*, staff_id: str | None) -> bool:
    """Web Agent 兼容：按 staffId 判断是否管理员。"""
    return is_admin(staff_id=staff_id)


def list_admin_permission_definitions() -> list[dict[str, str]]:
    return permission_definitions()


def web_admin_denial_message() -> str:
    return DENY_MESSAGE
