"""网页版 Agent：管理员权限（会话清空等高危操作）。"""

from __future__ import annotations

import sys
from pathlib import Path

_gateway = Path(__file__).resolve().parents[1] / "dingtalk_gateway"
if str(_gateway) not in sys.path:
    sys.path.insert(0, str(_gateway))

from admin_permission import (  # noqa: E402
    CHENMO_STAFF_ID,
    DENY_MESSAGE,
    _localhost_admin_staff_id,
    has_admin_permission,
    is_admin,
    is_protected_web_admin,
    is_web_admin,
    list_admin_permission_definitions,
    resolve_admin_user_id,
    web_admin_denial_message,
)

__all__ = [
    "CHENMO_STAFF_ID",
    "DENY_MESSAGE",
    "_localhost_admin_staff_id",
    "has_admin_permission",
    "is_admin",
    "is_protected_web_admin",
    "is_web_admin",
    "list_admin_permission_definitions",
    "resolve_admin_user_id",
    "web_admin_denial_message",
]
