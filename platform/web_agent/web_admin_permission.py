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

DENY_MESSAGE = "没有权限"


def is_web_admin(*, staff_id: str | None) -> bool:
    """是否网页版管理员（与网关代码修改白名单共用 staffId 列表）。"""
    uid = (staff_id or "").strip()
    if not uid:
        return False
    load_env_local()
    local_admin = os.environ.get("WEB_AGENT_LOCAL_ADMIN_STAFF_ID", "admin").strip() or "admin"
    if uid == local_admin:
        return True
    return is_code_modify_allowed(sender_staff_id=uid, sender_id=None)


def web_admin_denial_message() -> str:
    return DENY_MESSAGE
