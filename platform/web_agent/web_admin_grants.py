"""Web Agent 管理员细粒度权限存储与校验。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

WEB_AGENT_DIR = Path(__file__).resolve().parent
GRANTS_PATH = WEB_AGENT_DIR / "data" / "admin_grants.json"

PERMISSION_DEFS: tuple[dict[str, str], ...] = (
    {"key": "super_admin", "label": "超级管理员", "short": "超级管理员"},
    {"key": "code_modify", "label": "代码修改", "short": "改代码"},
    {"key": "source_file", "label": "源文件导出", "short": "源文件"},
    {"key": "online", "label": "操作线上环境", "short": "线上"},
)

SUPER_ADMIN_KEY = "super_admin"
# 与 code_modify_allowlist / web_admin_permission 一致
CHENMO_STAFF_ID = "32274159141215328"
GRANULAR_PERMISSION_KEYS: frozenset[str] = frozenset(
    item["key"] for item in PERMISSION_DEFS if item["key"] != SUPER_ADMIN_KEY
)
PERMISSION_KEYS: frozenset[str] = frozenset(item["key"] for item in PERMISSION_DEFS)


def permission_definitions() -> list[dict[str, str]]:
    return [dict(item) for item in PERMISSION_DEFS]


def _normalize_permission_keys(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    keys: list[str] = []
    for item in raw:
        key = str(item or "").strip()
        if key in PERMISSION_KEYS and key not in keys:
            keys.append(key)
    return keys


@lru_cache(maxsize=1)
def load_admin_grants() -> dict[str, list[str]]:
    if not GRANTS_PATH.is_file():
        return {}
    try:
        data = json.loads(GRANTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    grants: dict[str, list[str]] = {}
    for staff_id, permissions in data.items():
        uid = str(staff_id or "").strip()
        if not uid:
            continue
        grants[uid] = _normalize_permission_keys(permissions)
    return grants


def reload_admin_grants() -> dict[str, list[str]]:
    load_admin_grants.cache_clear()
    return load_admin_grants()


def has_explicit_admin_grants(staff_id: str) -> bool:
    uid = (staff_id or "").strip()
    if not uid:
        return False
    return uid in load_admin_grants()


def _is_builtin_super_admin(staff_id: str) -> bool:
    """内置超管：localhost admin 与陈墨。"""
    uid = (staff_id or "").strip()
    if not uid:
        return False
    if uid == CHENMO_STAFF_ID:
        return True
    try:
        from web_admin_permission import _localhost_admin_staff_id

        return uid == _localhost_admin_staff_id()
    except ImportError:
        return uid == "admin"


def is_super_admin(staff_id: str) -> bool:
    """是否超级管理员（内置 admin/陈墨，或 grants 勾选 super_admin）。"""
    uid = (staff_id or "").strip()
    if not uid:
        return False
    if _is_builtin_super_admin(uid):
        return True
    return SUPER_ADMIN_KEY in set(load_admin_grants().get(uid, []))


def list_super_admin_staff_ids() -> list[str]:
    """所有超级管理员的 staffId（内置 + grants，去重排序）。"""
    ids: set[str] = set()
    if CHENMO_STAFF_ID:
        ids.add(CHENMO_STAFF_ID)
    try:
        from web_admin_permission import _localhost_admin_staff_id

        local_id = _localhost_admin_staff_id()
        if local_id:
            ids.add(local_id)
    except ImportError:
        ids.add("admin")
    for staff_id, perms in load_admin_grants().items():
        if SUPER_ADMIN_KEY in set(perms):
            ids.add(staff_id)
    return sorted(ids)


def _legacy_full_granular_permissions() -> dict[str, bool]:
    base = {key: False for key in PERMISSION_KEYS}
    for key in GRANULAR_PERMISSION_KEYS:
        base[key] = True
    return base


def get_admin_permission_map(
    *,
    staff_id: str,
    is_admin: bool,
    protected: bool = False,
) -> dict[str, bool]:
    """返回各权限是否生效；非管理员全 False。"""
    base = {key: False for key in PERMISSION_KEYS}
    if not is_admin:
        return base
    if protected:
        return {key: True for key in PERMISSION_KEYS}

    uid = (staff_id or "").strip()
    grants = load_admin_grants()
    granted = set(grants.get(uid, []))
    if SUPER_ADMIN_KEY in granted:
        return {key: True for key in PERMISSION_KEYS}

    if uid not in grants:
        # 历史管理员：未单独配置时保留全部细粒度权限
        return _legacy_full_granular_permissions()

    return {key: key in granted for key in PERMISSION_KEYS}


def save_admin_permissions(*, staff_id: str, permissions: dict[str, bool]) -> list[str]:
    """持久化目标管理员的权限勾选；返回已保存的权限 key 列表。"""
    uid = (staff_id or "").strip()
    if not uid:
        raise ValueError("staff_id 不能为空")

    if permissions.get(SUPER_ADMIN_KEY) is True:
        selected = [SUPER_ADMIN_KEY]
    else:
        selected = [
            item["key"]
            for item in PERMISSION_DEFS
            if item["key"] != SUPER_ADMIN_KEY and permissions.get(item["key"]) is True
        ]

    grants = dict(load_admin_grants())
    grants[uid] = selected
    GRANTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRANTS_PATH.write_text(
        json.dumps(grants, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    reload_admin_grants()
    return selected


def remove_admin_grants(staff_id: str) -> None:
    uid = (staff_id or "").strip()
    if not uid:
        return
    grants = dict(load_admin_grants())
    if uid not in grants:
        return
    grants.pop(uid, None)
    GRANTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRANTS_PATH.write_text(
        json.dumps(grants, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    reload_admin_grants()


def init_admin_grants_empty(staff_id: str) -> None:
    """新授予管理员时写入空权限（需逐项勾选）。"""
    uid = (staff_id or "").strip()
    if not uid:
        return
    grants = dict(load_admin_grants())
    if uid in grants:
        return
    grants[uid] = []
    GRANTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRANTS_PATH.write_text(
        json.dumps(grants, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    reload_admin_grants()


def grants_payload_for_api() -> dict[str, Any]:
    return {
        "definitions": permission_definitions(),
        "keys": sorted(PERMISSION_KEYS),
    }
