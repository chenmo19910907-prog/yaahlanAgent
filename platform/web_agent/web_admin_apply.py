"""Web Agent 管理员申请：钉钉通知审批人，同意后写入代码修改白名单。"""

from __future__ import annotations

import json
import logging
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("web-agent")

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
APPLICATIONS_PATH = WEB_AGENT_DIR / "data" / "admin_applications.json"
TOKEN_LEN = 8
PENDING_TTL_HOURS = 72


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _gateway_import():
    if str(GATEWAY_DIR) not in sys.path:
        sys.path.insert(0, str(GATEWAY_DIR))
    from code_modify_permission import (  # noqa: WPS433
        add_staff_to_local_allowlist,
        get_admin_notify_staff_ids,
        is_code_modify_allowed,
    )

    return add_staff_to_local_allowlist, get_admin_notify_staff_ids, is_code_modify_allowed


def _load_applications(path: Path | None = None) -> dict[str, Any]:
    target = path or APPLICATIONS_PATH
    if not target.is_file():
        return {"applications": []}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"applications": []}
        apps = data.get("applications")
        if not isinstance(apps, list):
            return {"applications": []}
        return {"applications": apps}
    except (OSError, json.JSONDecodeError):
        return {"applications": []}


def _save_applications(data: dict[str, Any], path: Path | None = None) -> None:
    target = path or APPLICATIONS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _normalize_application(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    token = str(raw.get("token") or "").strip().lower()
    staff_id = str(raw.get("staffId") or "").strip()
    if not token or not staff_id:
        return None
    display_name = str(raw.get("displayName") or "").strip()
    status = str(raw.get("status") or "pending").strip().lower()
    if status not in {"pending", "approved", "rejected"}:
        status = "pending"
    return {
        "token": token,
        "staffId": staff_id,
        "displayName": display_name,
        "status": status,
        "createdAt": str(raw.get("createdAt") or "").strip() or _utc_now_iso(),
        "resolvedAt": str(raw.get("resolvedAt") or "").strip(),
        "resolvedBy": str(raw.get("resolvedBy") or "").strip(),
    }


def _new_token(existing: set[str]) -> str:
    for _ in range(32):
        token = secrets.token_hex(TOKEN_LEN // 2)
        if token not in existing:
            return token
    raise RuntimeError("无法生成唯一申请 token")


def find_pending_for_staff(staff_id: str, *, path: Path | None = None) -> dict[str, Any] | None:
    uid = (staff_id or "").strip()
    if not uid:
        return None
    for raw in _load_applications(path).get("applications", []):
        app = _normalize_application(raw)
        if app and app["staffId"] == uid and app["status"] == "pending":
            return app
    return None


def find_application_by_token(token: str, *, path: Path | None = None) -> dict[str, Any] | None:
    key = (token or "").strip().lower()
    if not key:
        return None
    for raw in _load_applications(path).get("applications", []):
        app = _normalize_application(raw)
        if app and app["token"] == key:
            return app
    return None


def application_status_for_staff(staff_id: str, *, path: Path | None = None) -> dict[str, Any]:
    _, _, is_allowed = _gateway_import()
    uid = (staff_id or "").strip()
    if not uid:
        return {"status": "none"}
    if is_allowed(sender_staff_id=uid, sender_id=None):
        return {"status": "approved", "isAdmin": True}
    pending = find_pending_for_staff(uid, path=path)
    if pending:
        return {
            "status": "pending",
            "token": pending["token"],
            "createdAt": pending["createdAt"],
        }
    return {"status": "none"}


def _notify_admin(application: dict[str, Any], *, client: Any | None = None) -> None:
    _, get_notify_ids, _ = _gateway_import()
    notify_ids = get_notify_ids()
    if not notify_ids:
        raise RuntimeError("未配置管理员通知接收人")

    name = application.get("displayName") or application["staffId"]
    staff_id = application["staffId"]
    token = application["token"]
    body = (
        f"### Web Agent 管理员申请\n\n"
        f"- **申请人**：{name}\n"
        f"- **staffId**：`{staff_id}`\n"
        f"- **申请码**：`{token}`\n\n"
        f"同意请回复：**同意管理员申请 {token}**\n\n"
        f"拒绝请回复：**拒绝管理员申请 {token}**"
    )
    if str(GATEWAY_DIR) not in sys.path:
        sys.path.insert(0, str(GATEWAY_DIR))
    from dingtalk_private_message import send_robot_private_markdown  # noqa: WPS433

    errors: list[str] = []
    for admin_id in notify_ids:
        try:
            send_robot_private_markdown(
                admin_id,
                "Web Agent 管理员申请",
                body,
                client=client,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("管理员申请通知失败 admin=%s", admin_id[:12])
            errors.append(str(exc))
    if len(errors) == len(notify_ids):
        raise RuntimeError(errors[0] if errors else "钉钉通知发送失败")


def _notify_applicant(staff_id: str, *, approved: bool, client: Any | None = None) -> None:
    if str(GATEWAY_DIR) not in sys.path:
        sys.path.insert(0, str(GATEWAY_DIR))
    from dingtalk_private_message import send_robot_private_text  # noqa: WPS433

    if approved:
        text = (
            "你的 Web Agent 管理员申请已通过。\n"
            "请刷新网页后即可使用管理员能力（改代码、清空会话等）。"
        )
    else:
        text = "你的 Web Agent 管理员申请未通过，如有疑问请联系管理员。"
    try:
        send_robot_private_text(staff_id, text, client=client)
    except Exception as exc:  # noqa: BLE001
        logger.warning("申请人结果通知失败 staff=%s: %s", staff_id[:12], exc)


def submit_application(
    *,
    staff_id: str,
    display_name: str = "",
    client: Any | None = None,
    path: Path | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """提交管理员申请。返回 (application, error)。"""
    _, _, is_allowed = _gateway_import()
    uid = (staff_id or "").strip()
    if not uid:
        return None, "无法识别登录身份"
    if uid.startswith("guest_"):
        return None, "访客无法申请管理员，请使用钉钉账号登录"
    if is_allowed(sender_staff_id=uid, sender_id=None):
        return None, "你已是管理员"

    pending = find_pending_for_staff(uid, path=path)
    if pending:
        return pending, None

    data = _load_applications(path)
    apps = [_normalize_application(x) for x in data.get("applications", [])]
    apps = [x for x in apps if x is not None]
    existing_tokens = {str(x["token"]) for x in apps}
    application = {
        "token": _new_token(existing_tokens),
        "staffId": uid,
        "displayName": (display_name or "").strip() or uid,
        "status": "pending",
        "createdAt": _utc_now_iso(),
        "resolvedAt": "",
        "resolvedBy": "",
    }
    apps.append(application)
    _save_applications({"applications": apps}, path=path)

    try:
        _notify_admin(application, client=client)
    except Exception as exc:  # noqa: BLE001
        logger.exception("管理员申请钉钉通知失败 staff=%s", uid[:12])
        return application, f"申请已记录，但钉钉通知失败：{exc}"

    logger.info("管理员申请已提交 staff=%s token=%s", uid[:12], application["token"])
    return application, None


def resolve_application(
    *,
    token: str,
    approver_staff_id: str,
    approve: bool,
    client: Any | None = None,
    path: Path | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """审批管理员申请。返回 (application, error)。"""
    add_staff, get_notify_ids, is_allowed = _gateway_import()
    approver = (approver_staff_id or "").strip()
    if not approver:
        return None, "无法识别审批人身份"
    notify_ids = set(get_notify_ids())
    if notify_ids and approver not in notify_ids and not is_allowed(
        sender_staff_id=approver,
        sender_id=None,
    ):
        return None, "你没有审批管理员申请的权限"

    app = find_application_by_token(token, path=path)
    if not app:
        return None, f"未找到申请码 {token!r}"
    if app["status"] != "pending":
        return None, f"申请已处理（{app['status']}）"

    data = _load_applications(path)
    updated: dict[str, Any] | None = None
    now = _utc_now_iso()
    new_apps: list[dict[str, Any]] = []
    for raw in data.get("applications", []):
        item = _normalize_application(raw)
        if not item:
            continue
        if item["token"] == app["token"]:
            item["status"] = "approved" if approve else "rejected"
            item["resolvedAt"] = now
            item["resolvedBy"] = approver
            updated = item
        new_apps.append(item)
    if updated is None:
        return None, "申请记录异常"

    if approve:
        add_staff(updated["staffId"])

    _save_applications({"applications": new_apps}, path=path)
    _notify_applicant(updated["staffId"], approved=approve, client=client)
    logger.info(
        "管理员申请已%s token=%s applicant=%s approver=%s",
        "通过" if approve else "拒绝",
        updated["token"],
        updated["staffId"][:12],
        approver[:12],
    )
    return updated, None


def handle_admin_apply_decision(
    *,
    text: str,
    sender_staff_id: str,
    client: Any | None = None,
) -> str:
    if str(GATEWAY_DIR) not in sys.path:
        sys.path.insert(0, str(GATEWAY_DIR))
    from route_patterns import parse_admin_apply_decision  # noqa: WPS433

    parsed = parse_admin_apply_decision(text)
    if not parsed:
        return "无法解析审批指令，请使用：同意管理员申请 <申请码>"
    token, approve = parsed
    app, err = resolve_application(
        token=token,
        approver_staff_id=sender_staff_id,
        approve=approve,
        client=client,
    )
    if err:
        return err
    assert app is not None
    name = app.get("displayName") or app["staffId"]
    if approve:
        return f"已同意 {name}（{app['staffId']}）的管理员申请。"
    return f"已拒绝 {name}（{app['staffId']}）的管理员申请。"
