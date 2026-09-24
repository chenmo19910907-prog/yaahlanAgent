"""Web Agent 管理员列表操作审计日志。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WEB_AGENT_DIR = Path(__file__).resolve().parent
AUDIT_LOG_PATH = WEB_AGENT_DIR / "data" / "admin_audit_log.json"
MAX_ENTRIES = 500

ACTION_LABELS: dict[str, str] = {
    "grant_admin": "设为管理员",
    "revoke_admin": "撤销管理员",
    "update_permissions": "更新权限",
    "quit_admin": "主动退出管理员",
    "apply_admin": "申请管理员",
    "remove_user": "从列表移除",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_target_display_name(staff_id: str) -> str:
    uid = (staff_id or "").strip()
    if not uid:
        return ""
    try:
        from dingtalk_user_lookup import lookup_auth_user_display_name

        return lookup_auth_user_display_name(uid, "")
    except Exception:  # noqa: BLE001
        return uid


def _load_entries() -> list[dict[str, Any]]:
    if not AUDIT_LOG_PATH.is_file():
        return []
    try:
        data = json.loads(AUDIT_LOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _save_entries(entries: list[dict[str, Any]]) -> None:
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    trimmed = entries[-MAX_ENTRIES:]
    AUDIT_LOG_PATH.write_text(
        json.dumps(trimmed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _permission_label(key: str) -> str:
    try:
        from web_admin_grants import PERMISSION_DEFS

        for item in PERMISSION_DEFS:
            if item["key"] == key:
                return item["label"]
    except Exception:  # noqa: BLE001
        pass
    return key


def describe_permission_changes(
    *,
    before: dict[str, bool],
    after: dict[str, bool],
) -> str:
    """生成权限变更描述。"""
    keys = sorted(set(before.keys()) | set(after.keys()))
    parts: list[str] = []
    for key in keys:
        old_val = before.get(key) is True
        new_val = after.get(key) is True
        if old_val == new_val:
            continue
        label = _permission_label(key)
        parts.append(f"{'开启' if new_val else '关闭'}「{label}」")
    return "、".join(parts) if parts else "无变更"


def append_admin_audit_entry(
    *,
    action: str,
    operator_staff_id: str,
    operator_display_name: str,
    target_staff_id: str,
    target_display_name: str = "",
    detail: str = "",
) -> dict[str, Any]:
    """追加一条管理员列表操作记录。"""
    action_key = (action or "").strip()
    if action_key not in ACTION_LABELS:
        raise ValueError(f"未知操作类型: {action_key}")

    target_id = (target_staff_id or "").strip()
    target_name = (target_display_name or "").strip() or _resolve_target_display_name(target_id)
    operator_id = (operator_staff_id or "").strip()
    operator_name = (operator_display_name or "").strip() or operator_id

    entry: dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "ts": _now_iso(),
        "action": action_key,
        "actionLabel": ACTION_LABELS[action_key],
        "operatorStaffId": operator_id,
        "operatorName": operator_name,
        "targetStaffId": target_id,
        "targetName": target_name,
        "detail": (detail or "").strip(),
    }
    entries = _load_entries()
    entries.append(entry)
    _save_entries(entries)
    return entry


def list_admin_audit_entries(*, limit: int = 100) -> dict[str, Any]:
    """返回最近的操作记录（时间倒序）。"""
    safe_limit = max(1, min(int(limit or 100), MAX_ENTRIES))
    entries = _load_entries()
    entries.sort(key=lambda item: str(item.get("ts") or ""), reverse=True)
    return {
        "entries": entries[:safe_limit],
        "total": len(entries),
    }
