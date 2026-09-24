"""Web Agent 管理员变更：钉钉机器人私聊通知目标用户。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("web-agent")

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"

GRANT_ADMIN_QUIT_HINT = "如需退出，可在管理员列表中主动退出管理员。"


def _permission_label(key: str) -> str:
    try:
        from web_admin_grants import PERMISSION_DEFS

        for item in PERMISSION_DEFS:
            if item["key"] == key:
                return item["label"]
    except Exception:  # noqa: BLE001
        pass
    return key


def split_permission_changes(
    *,
    before: dict[str, bool],
    after: dict[str, bool],
) -> tuple[list[str], list[str]]:
    """返回 (获得权限标签, 移除权限标签)。"""
    keys = sorted(set(before.keys()) | set(after.keys()))
    gained: list[str] = []
    removed: list[str] = []
    for key in keys:
        old_val = before.get(key) is True
        new_val = after.get(key) is True
        if old_val == new_val:
            continue
        label = _permission_label(key)
        if new_val:
            gained.append(label)
        else:
            removed.append(label)
    return gained, removed


def _format_permission_lines(gained: list[str], removed: list[str]) -> str:
    lines: list[str] = []
    if gained:
        lines.append("获得权限：" + "、".join(gained))
    if removed:
        lines.append("移除权限：" + "、".join(removed))
    if not lines:
        lines.append("权限无变更")
    return "\n".join(lines)


def build_admin_change_message(
    *,
    action: str,
    operator_display_name: str,
    gained: list[str] | None = None,
    removed: list[str] | None = None,
) -> str:
    """组装钉钉私聊正文。"""
    action_key = (action or "").strip()
    operator = (operator_display_name or "").strip() or "管理员"
    gained_list = list(gained or [])
    removed_list = list(removed or [])

    action_lines: dict[str, str] = {
        "grant_admin": "您已被设为 Web Agent 管理员",
        "revoke_admin": "您的 Web Agent 管理员身份已被撤销",
        "update_permissions": "您的 Web Agent 管理员权限已更新",
        "quit_admin": "您已退出 Web Agent 管理员",
    }
    headline = action_lines.get(action_key, "Web Agent 管理员信息已变更")

    if action_key == "revoke_admin" and not removed_list:
        removed_list = ["全部管理员权限"]

    parts = [headline, _format_permission_lines(gained_list, removed_list)]
    if action_key == "grant_admin":
        parts.append(GRANT_ADMIN_QUIT_HINT)
    if action_key == "quit_admin":
        return "\n\n".join(parts)
    parts.append(f"操作人：{operator}")
    return "\n\n".join(parts)


def _can_notify_staff(staff_id: str) -> bool:
    uid = (staff_id or "").strip()
    if not uid or uid.startswith("guest_"):
        return False
    try:
        from web_auth import localhost_admin_config

        local_id, _ = localhost_admin_config()
        if uid == (local_id or "admin").strip():
            return False
    except Exception:  # noqa: BLE001
        if uid == "admin":
            return False
    return True


def send_robot_private_text(staff_id: str, text: str, *, client: Any | None = None) -> None:
    """供测试 patch 的钉钉私聊发送入口。"""
    if str(GATEWAY_DIR) not in sys.path:
        sys.path.insert(0, str(GATEWAY_DIR))
    from dingtalk_private_message import send_robot_private_text as _send  # noqa: WPS433

    _send(staff_id, text, client=client)


def notify_admin_change(
    *,
    action: str,
    target_staff_id: str,
    target_display_name: str = "",
    operator_display_name: str = "",
    gained: list[str] | None = None,
    removed: list[str] | None = None,
    client: Any | None = None,
) -> bool:
    """向目标用户发送管理员变更钉钉私聊；失败仅记日志，不抛错。"""
    del target_display_name  # 私聊面向本人，正文统一用「您」
    uid = (target_staff_id or "").strip()
    if not _can_notify_staff(uid):
        return False

    text = build_admin_change_message(
        action=action,
        operator_display_name=operator_display_name,
        gained=gained,
        removed=removed,
    )
    try:
        send_robot_private_text(uid, text, client=client)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "管理员变更钉钉通知失败 action=%s target=%s…: %s",
            action,
            uid[:12],
            exc,
        )
        return False

    logger.info(
        "管理员变更已通知钉钉 action=%s target=%s…",
        action,
        uid[:12],
    )
    return True


def list_notifiable_admin_staff_ids() -> list[str]:
    """当前所有可钉钉通知的管理员 staffId（去重排序）。"""
    if str(GATEWAY_DIR) not in sys.path:
        sys.path.insert(0, str(GATEWAY_DIR))
    from code_modify_permission import load_code_modify_allowlist  # noqa: WPS433

    cfg = load_code_modify_allowlist()
    return sorted(uid for uid in cfg.allowed_staff_ids if _can_notify_staff(uid))


def broadcast_quit_admin_hint(*, client: Any | None = None) -> dict[str, Any]:
    """向现有全部管理员单独发送退出提示；返回 sent / failed 统计。"""
    text = GRANT_ADMIN_QUIT_HINT
    sent: list[str] = []
    failed: list[dict[str, str]] = []
    for uid in list_notifiable_admin_staff_ids():
        try:
            send_robot_private_text(uid, text, client=client)
        except Exception as exc:  # noqa: BLE001
            logger.warning("管理员退出提示发送失败 staff=%s…: %s", uid[:12], exc)
            failed.append({"staffId": uid, "error": str(exc)})
            continue
        sent.append(uid)
        logger.info("管理员退出提示已发送 staff=%s…", uid[:12])
    return {"sent": sent, "failed": failed, "total": len(sent) + len(failed)}


def notify_permission_map_change(
    *,
    action: str,
    target_staff_id: str,
    target_display_name: str,
    operator_display_name: str,
    before: dict[str, bool],
    after: dict[str, bool],
    client: Any | None = None,
) -> bool:
    """根据权限 map 前后差异发送通知。"""
    gained, removed = split_permission_changes(before=before, after=after)
    return notify_admin_change(
        action=action,
        target_staff_id=target_staff_id,
        target_display_name=target_display_name,
        operator_display_name=operator_display_name,
        gained=gained,
        removed=removed,
        client=client,
    )
