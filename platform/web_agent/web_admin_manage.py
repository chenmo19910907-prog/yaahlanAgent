"""Web Agent 管理员列表：查看全员身份；admin / 陈墨 可授予或撤销管理员。"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from code_modify_permission import (  # noqa: E402
    add_staff_to_local_allowlist,
    is_code_modify_allowed,
    is_staff_in_base_allowlist,
    load_code_modify_allowlist,
    remove_staff_from_local_allowlist,
)
from web_admin_grants import (
    get_admin_permission_map,
    grants_payload_for_api,
    init_admin_grants_empty,
    is_super_admin,
    load_admin_grants,
    permission_definitions,
    remove_admin_grants,
    save_admin_permissions,
)
from web_admin_permission import is_protected_web_admin, is_web_admin  # noqa: E402

# 陈墨（钉钉 staffId，与 code_modify_allowlist.json 一致）
CHENMO_STAFF_ID = "32274159141215328"
HIDDEN_USERS_PATH = WEB_AGENT_DIR / "data" / "admin_list_hidden.json"


def _localhost_admin_staff_id() -> str:
    try:
        from web_auth import localhost_admin_config

        staff_id, _ = localhost_admin_config()
        return (staff_id or "admin").strip() or "admin"
    except Exception:  # noqa: BLE001
        return "admin"


def _is_chenmo_account(*, staff_id: str, display_name: str = "") -> bool:
    uid = (staff_id or "").strip()
    if uid == CHENMO_STAFF_ID:
        return True
    try:
        from dingtalk_user_lookup import chinese_display_name

        plain = chinese_display_name(display_name or "")
        return plain == "陈墨"
    except Exception:  # noqa: BLE001
        return (display_name or "").strip() == "陈墨"


def can_manage_admin_roles(*, staff_id: str, display_name: str = "") -> bool:
    """admin / 陈墨 / 超级管理员可修改他人管理员身份。"""
    uid = (staff_id or "").strip()
    if not uid:
        return False
    if uid == _localhost_admin_staff_id():
        return True
    if _is_chenmo_account(staff_id=uid, display_name=display_name):
        return True
    return is_super_admin(uid)


def is_protected_admin_account(staff_id: str) -> bool:
    """不可被撤销管理员的核心账号。"""
    return is_protected_web_admin(staff_id)


@lru_cache(maxsize=1)
def load_admin_list_hidden_staff_ids() -> frozenset[str]:
    if not HIDDEN_USERS_PATH.is_file():
        return frozenset()
    try:
        data = json.loads(HIDDEN_USERS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    if not isinstance(data, list):
        return frozenset()
    return frozenset(
        str(item or "").strip()
        for item in data
        if str(item or "").strip()
    )


def reload_admin_list_hidden_staff_ids() -> frozenset[str]:
    load_admin_list_hidden_staff_ids.cache_clear()
    return load_admin_list_hidden_staff_ids()


def _save_admin_list_hidden_staff_ids(staff_ids: set[str]) -> None:
    HIDDEN_USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(staff_ids)
    HIDDEN_USERS_PATH.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    reload_admin_list_hidden_staff_ids()


def _collect_all_users() -> list[dict[str, str]]:
    """汇总可选人员；打开管理员列表时不触发钉钉通讯录网络刷新。"""
    from dingtalk_user_lookup import collect_cached_staff_labels, is_selectable_collaborator
    from web_session_store import get_session_store

    store = get_session_store()
    sessions = store.list_sessions(enrich_names=False)
    known = collect_cached_staff_labels(sessions, allow_org_roster_network=False)

    cfg = load_code_modify_allowlist()
    for uid in cfg.allowed_staff_ids:
        known.setdefault(uid, uid)
    for uid in load_admin_grants():
        known.setdefault(uid, uid)

    hidden = load_admin_list_hidden_staff_ids()
    localhost_admin = _localhost_admin_staff_id()
    users: list[dict[str, str]] = []
    for uid, label in known.items():
        staff_id = (uid or "").strip()
        if not staff_id or staff_id.startswith("guest_"):
            continue
        if staff_id == localhost_admin:
            continue
        display_name = (label or staff_id).strip() or staff_id
        if staff_id in hidden:
            continue
        if not is_selectable_collaborator(staff_id, display_name):
            continue
        users.append(
            {
                "staffId": staff_id,
                "displayName": display_name,
            }
        )
    users.sort(key=lambda item: (item["displayName"], item["staffId"]))
    return users


def enrich_selectable_users_with_admin_roles(
    users: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """为选人列表补充 isAdmin / isSuperAdmin，供共同对话与分享钉钉展示角色标签。"""
    cfg = load_code_modify_allowlist()
    allowed_staff = cfg.allowed_staff_ids
    localhost_admin = _localhost_admin_staff_id()
    enriched: list[dict[str, Any]] = []
    for user in users:
        staff_id = (user.get("staffId") or "").strip()
        is_admin = staff_id == localhost_admin or staff_id in allowed_staff
        enriched.append(
            {
                **user,
                "isAdmin": is_admin,
                "isSuperAdmin": is_super_admin(staff_id) if is_admin else False,
            }
        )
    return enriched


def _admin_list_sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
    """内置超管（陈墨）最前，其次其他超管、管理员、普通用户；同组按姓名。"""
    if item.get("protected") and item.get("isSuperAdmin"):
        tier = 0
    elif item.get("isSuperAdmin"):
        tier = 1
    elif item.get("isAdmin"):
        tier = 2
    else:
        tier = 3
    return (tier, item["displayName"], item["staffId"])


def list_admin_users(*, viewer_staff_id: str, viewer_display_name: str = "") -> dict[str, Any]:
    """返回管理员列表及当前查看者是否可编辑。"""
    users = _collect_all_users()
    cfg = load_code_modify_allowlist()
    allowed_staff = cfg.allowed_staff_ids
    localhost_admin = _localhost_admin_staff_id()
    items: list[dict[str, Any]] = []
    for user in users:
        staff_id = user["staffId"]
        is_admin = staff_id == localhost_admin or staff_id in allowed_staff
        protected = is_protected_admin_account(staff_id)
        super_admin = is_super_admin(staff_id)
        items.append(
            {
                "staffId": staff_id,
                "displayName": user["displayName"],
                "isAdmin": is_admin,
                "isSuperAdmin": super_admin,
                "protected": protected,
                "canQuit": can_quit_admin_role(staff_id),
                "permissions": get_admin_permission_map(
                    staff_id=staff_id,
                    is_admin=is_admin,
                    protected=protected,
                ),
            }
        )
    items.sort(key=_admin_list_sort_key)
    payload = grants_payload_for_api()
    return {
        "users": items,
        "total": len(items),
        "canManage": can_manage_admin_roles(
            staff_id=viewer_staff_id,
            display_name=viewer_display_name,
        ),
        "permissionDefinitions": payload["definitions"],
    }


def can_quit_admin_role(staff_id: str) -> bool:
    """普通管理员是否可自助退出（非受保护、非主配置登记）。"""
    target = (staff_id or "").strip()
    if not target or target.startswith("guest_"):
        return False
    if not is_web_admin(staff_id=target):
        return False
    if is_protected_admin_account(target):
        return False
    if is_staff_in_base_allowlist(target):
        return False
    cfg = load_code_modify_allowlist()
    return target in cfg.allowed_staff_ids


def quit_admin_role(*, staff_id: str) -> tuple[dict[str, Any] | None, str | None]:
    """当前用户自助退出管理员身份。"""
    target = (staff_id or "").strip()
    if not target:
        return None, "缺少 staffId"
    if target.startswith("guest_"):
        return None, "访客账号无法退出管理员"
    if not can_quit_admin_role(target):
        return None, "该账号不可退出管理员"

    removed = remove_staff_from_local_allowlist(target)
    if not removed:
        return None, "该用户不在可撤销的管理员列表中"
    remove_admin_grants(target)
    return {"staffId": target, "isAdmin": False}, None


def set_admin_role(
    *,
    operator_staff_id: str,
    operator_display_name: str,
    target_staff_id: str,
    is_admin: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    """授予或撤销目标用户管理员身份。"""
    if not can_manage_admin_roles(
        staff_id=operator_staff_id,
        display_name=operator_display_name,
    ):
        return None, "没有权限"

    target = (target_staff_id or "").strip()
    if not target:
        return None, "缺少 staffId"
    if target.startswith("guest_"):
        return None, "访客账号无法设为管理员"

    if not is_admin and is_protected_admin_account(target):
        return None, "该账号不可撤销管理员"

    if is_admin:
        if is_code_modify_allowed(sender_staff_id=target, sender_id=None):
            init_admin_grants_empty(target)
            return {"staffId": target, "isAdmin": True}, None
        add_staff_to_local_allowlist(target)
        init_admin_grants_empty(target)
        return {"staffId": target, "isAdmin": True}, None

    if not is_code_modify_allowed(sender_staff_id=target, sender_id=None):
        return None, "该用户不是管理员"

    if is_staff_in_base_allowlist(target):
        return None, "该用户在主配置中登记，无法在此撤销"

    removed = remove_staff_from_local_allowlist(target)
    if not removed:
        return None, "该用户不在可撤销的管理员列表中"
    remove_admin_grants(target)
    return {"staffId": target, "isAdmin": False}, None


def set_admin_permissions(
    *,
    operator_staff_id: str,
    operator_display_name: str,
    target_staff_id: str,
    permissions: dict[str, bool],
) -> tuple[dict[str, Any] | None, str | None]:
    """更新目标管理员的细粒度权限。"""
    if not can_manage_admin_roles(
        staff_id=operator_staff_id,
        display_name=operator_display_name,
    ):
        return None, "没有权限"

    target = (target_staff_id or "").strip()
    if not target:
        return None, "缺少 staffId"
    if not is_web_admin(staff_id=target):
        return None, "该用户不是管理员"
    if is_protected_admin_account(target):
        return None, "该账号权限不可修改"

    normalized: dict[str, bool] = {}
    for item in permission_definitions():
        key = item["key"]
        normalized[key] = permissions.get(key) is True

    saved = save_admin_permissions(staff_id=target, permissions=normalized)
    perm_map = get_admin_permission_map(
        staff_id=target,
        is_admin=True,
        protected=False,
    )
    return {
        "staffId": target,
        "permissions": perm_map,
        "grantedKeys": saved,
        "isSuperAdmin": is_super_admin(target),
    }, None


def remove_admin_list_user(
    *,
    operator_staff_id: str,
    operator_display_name: str,
    target_staff_id: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """从管理员列表移除普通用户（不删会话，仅隐藏）。"""
    if not can_manage_admin_roles(
        staff_id=operator_staff_id,
        display_name=operator_display_name,
    ):
        return None, "没有权限"

    target = (target_staff_id or "").strip()
    if not target:
        return None, "缺少 staffId"
    if is_protected_admin_account(target):
        return None, "该账号不可移除"
    if is_web_admin(staff_id=target):
        return None, "请先撤销管理员身份"

    hidden = set(load_admin_list_hidden_staff_ids())
    if target in hidden:
        return {"staffId": target, "removed": True}, None
    hidden.add(target)
    _save_admin_list_hidden_staff_ids(hidden)
    return {"staffId": target, "removed": True}, None
