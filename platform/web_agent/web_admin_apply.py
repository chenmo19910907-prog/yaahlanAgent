"""Web Agent 管理员申请：通知超级管理员，由超管在后台手动添加。"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("web-agent")

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
NOTIFICATIONS_PATH = WEB_AGENT_DIR / "data" / "admin_apply_notifications.json"
NOTIFY_DEDUP_HOURS = 24


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _gateway_import():
    if str(GATEWAY_DIR) not in sys.path:
        sys.path.insert(0, str(GATEWAY_DIR))
    from code_modify_permission import is_code_modify_allowed  # noqa: WPS433

    return is_code_modify_allowed


def _load_notifications(path: Path | None = None) -> dict[str, str]:
    target = path or NOTIFICATIONS_PATH
    if not target.is_file():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    raw = data.get("lastNotifyAt")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for staff_id, ts in raw.items():
        uid = str(staff_id or "").strip()
        stamp = str(ts or "").strip()
        if uid and stamp:
            out[uid] = stamp
    return out


def _save_notifications(notify_map: dict[str, str], path: Path | None = None) -> None:
    target = path or NOTIFICATIONS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"lastNotifyAt": notify_map}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _parse_iso(ts: str) -> datetime | None:
    text = (ts or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _recently_notified(staff_id: str, *, path: Path | None = None) -> bool:
    uid = (staff_id or "").strip()
    if not uid:
        return False
    stamp = _load_notifications(path).get(uid)
    if not stamp:
        return False
    notified_at = _parse_iso(stamp)
    if notified_at is None:
        return False
    if notified_at.tzinfo is None:
        notified_at = notified_at.replace(tzinfo=timezone.utc)
    return _utc_now() - notified_at < timedelta(hours=NOTIFY_DEDUP_HOURS)


def _record_notification(staff_id: str, *, path: Path | None = None) -> None:
    uid = (staff_id or "").strip()
    if not uid:
        return
    notify_map = _load_notifications(path)
    notify_map[uid] = _utc_now_iso()
    _save_notifications(notify_map, path=path)


def application_status_for_staff(staff_id: str, *, path: Path | None = None) -> dict[str, Any]:
    is_allowed = _gateway_import()
    uid = (staff_id or "").strip()
    if not uid:
        return {"status": "none"}
    if is_allowed(sender_staff_id=uid, sender_id=None):
        return {"status": "approved", "isAdmin": True}
    return {"status": "none"}


def _notify_super_admins(
    *,
    display_name: str,
    staff_id: str,
    client: Any | None = None,
) -> None:
    from web_admin_grants import list_super_admin_staff_ids  # noqa: WPS433

    notify_ids = list_super_admin_staff_ids()
    if not notify_ids:
        raise RuntimeError("未找到超级管理员")

    name = (display_name or "").strip() or staff_id
    text = f"{name}申请成为管理员"
    if str(GATEWAY_DIR) not in sys.path:
        sys.path.insert(0, str(GATEWAY_DIR))
    from dingtalk_private_message import send_robot_private_text  # noqa: WPS433

    errors: list[str] = []
    for admin_id in notify_ids:
        if admin_id == staff_id:
            continue
        try:
            send_robot_private_text(admin_id, text, client=client)
        except Exception as exc:  # noqa: BLE001
            logger.exception("管理员申请通知失败 admin=%s", admin_id[:12])
            errors.append(str(exc))
    if len(errors) == len([aid for aid in notify_ids if aid != staff_id]):
        raise RuntimeError(errors[0] if errors else "钉钉通知发送失败")


def submit_application(
    *,
    staff_id: str,
    display_name: str = "",
    client: Any | None = None,
    path: Path | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """提交管理员申请：通知超管，无 pending 状态。返回 (result, error)。"""
    is_allowed = _gateway_import()
    uid = (staff_id or "").strip()
    if not uid:
        return None, "无法识别登录身份"
    if uid.startswith("guest_"):
        return None, "访客无法申请管理员，请使用钉钉账号登录"
    if is_allowed(sender_staff_id=uid, sender_id=None):
        return None, "你已是管理员"

    if _recently_notified(uid, path=path):
        logger.info("管理员申请通知跳过（24h 内已发） staff=%s", uid[:12])
        return {"notified": False, "skippedDuplicate": True}, None

    try:
        _notify_super_admins(
            display_name=(display_name or "").strip() or uid,
            staff_id=uid,
            client=client,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("管理员申请钉钉通知失败 staff=%s", uid[:12])
        return None, f"钉钉通知失败：{exc}"

    _record_notification(uid, path=path)
    logger.info("管理员申请已通知超管 staff=%s", uid[:12])
    return {"notified": True}, None


def handle_admin_apply_decision(
    *,
    text: str,
    sender_staff_id: str,
    client: Any | None = None,
) -> str:
    del text, sender_staff_id, client
    return (
        "管理员申请已改为由超级管理员在 Web Agent 后台手动添加。"
        "请在用户头像信息中打开「管理员列表」进行授权。"
    )
