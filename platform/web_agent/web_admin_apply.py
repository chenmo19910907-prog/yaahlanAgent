"""Web Agent 管理员申请：钉钉卡片通知超管，口令或卡片按钮审批。"""

from __future__ import annotations

import json
import logging
import secrets
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any
from urllib.parse import quote

from web_admin_grants import (  # noqa: E402
    GRANULAR_PERMISSION_KEYS,
    SUPER_ADMIN_KEY,
    permission_definitions,
)

from web_admin_audit_log import append_admin_audit_entry

logger = logging.getLogger("web-agent")

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
NOTIFICATIONS_PATH = WEB_AGENT_DIR / "data" / "admin_apply_notifications.json"
APPLICATIONS_PATH = WEB_AGENT_DIR / "data" / "admin_applications.json"
APPLY_DEDUP_TZ = ZoneInfo("Asia/Shanghai")
TOKEN_LEN = 8


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


def _load_applications(path: Path | None = None) -> dict[str, Any]:
    target = path or APPLICATIONS_PATH
    if not target.is_file():
        return {"applications": []}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"applications": []}
    if not isinstance(data, dict):
        return {"applications": []}
    apps = data.get("applications")
    if not isinstance(apps, list):
        return {"applications": []}
    return {"applications": apps}


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
    if status not in {"pending", "approved", "rejected", "superseded"}:
        status = "pending"
    requested = _normalize_applicant_permission_keys(raw.get("requestedPermissions"))
    granted = _normalize_applicant_permission_keys(raw.get("grantedPermissions"))
    return {
        "token": token,
        "staffId": staff_id,
        "displayName": display_name,
        "status": status,
        "createdAt": str(raw.get("createdAt") or "").strip() or _utc_now_iso(),
        "resolvedAt": str(raw.get("resolvedAt") or "").strip(),
        "resolvedBy": str(raw.get("resolvedBy") or "").strip(),
        "requestedPermissions": requested,
        "grantedPermissions": granted,
    }


def _permission_label_map() -> dict[str, str]:
    return {
        str(item["key"]): str(item.get("label") or item["key"])
        for item in permission_definitions()
    }


def _normalize_applicant_permission_keys(raw: object) -> list[str]:
    """申请人/审批可勾选的细粒度权限（不含超级管理员）。"""
    if not isinstance(raw, list):
        return []
    keys: list[str] = []
    for item in raw:
        key = str(item or "").strip()
        if key in GRANULAR_PERMISSION_KEYS and key not in keys:
            keys.append(key)
    return keys


def _format_permission_keys(keys: list[str]) -> str:
    labels = _permission_label_map()
    if not keys:
        return "（未勾选具体权限，仅申请管理员身份）"
    return "、".join(labels.get(k, k) for k in keys)


def _permissions_dict_from_keys(keys: list[str]) -> dict[str, bool]:
    base = {item["key"]: False for item in permission_definitions()}
    for key in keys:
        if key in base:
            base[key] = True
    base[SUPER_ADMIN_KEY] = False
    return base


def application_review_payload(
    token: str,
    *,
    viewer_staff_id: str,
    viewer_display_name: str = "",
    path: Path | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    from web_admin_manage import can_manage_admin_roles  # noqa: WPS433

    viewer = (viewer_staff_id or "").strip()
    if not viewer:
        return None, "未登录"
    name = (viewer_display_name or "").strip() or viewer
    if not can_manage_admin_roles(staff_id=viewer, display_name=name):
        return None, "你没有审批管理员申请的权限"

    app = find_application_by_token(token, path=path)
    if not app:
        return None, f"未找到申请码 {token!r}"
    return {
        "token": app["token"],
        "staffId": app["staffId"],
        "displayName": app.get("displayName") or app["staffId"],
        "status": app["status"],
        "createdAt": app.get("createdAt") or "",
        "requestedPermissions": app.get("requestedPermissions") or [],
        "permissionDefinitions": [
            item
            for item in permission_definitions()
            if item["key"] in GRANULAR_PERMISSION_KEYS
        ],
    }, None


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
        if (
            app
            and app["staffId"] == uid
            and app["status"] == "pending"
            and _is_same_local_calendar_day(app.get("createdAt") or "")
        ):
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


def _parse_iso(ts: str) -> datetime | None:
    text = (ts or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _local_calendar_date(ts: str) -> date | None:
    dt = _parse_iso(ts)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(APPLY_DEDUP_TZ).date()


def _today_local() -> date:
    return _utc_now().astimezone(APPLY_DEDUP_TZ).date()


def _is_same_local_calendar_day(ts: str, *, ref: date | None = None) -> bool:
    day = _local_calendar_date(ts)
    if day is None:
        return False
    return day == (ref if ref is not None else _today_local())


def _recently_notified(staff_id: str, *, path: Path | None = None) -> bool:
    uid = (staff_id or "").strip()
    if not uid:
        return False
    stamp = _load_notifications(path).get(uid)
    if not stamp:
        return False
    return _is_same_local_calendar_day(stamp)


def _supersede_other_pending(
    apps: list[dict[str, Any]],
    *,
    staff_id: str,
    keep_token: str,
    now_iso: str,
) -> None:
    uid = (staff_id or "").strip()
    keep = (keep_token or "").strip().lower()
    for item in apps:
        if item["staffId"] != uid or item["status"] != "pending":
            continue
        if item["token"] == keep:
            continue
        item["status"] = "superseded"
        item["resolvedAt"] = now_iso
        item["resolvedBy"] = "system"


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
    pending = find_pending_for_staff(uid, path=path)
    if pending:
        return {
            "status": "pending",
            "token": pending["token"],
            "createdAt": pending["createdAt"],
            "requestedPermissions": pending.get("requestedPermissions") or [],
        }
    return {"status": "none"}


def _dtmd_robot_message(content: str) -> str:
    return f"dtmd://dingtalkclient/sendMessage?content={quote(content, safe='')}"


def _build_apply_card_body(application: dict[str, Any]) -> str:
    name = application.get("displayName") or application["staffId"]
    staff_id = application["staffId"]
    token = application["token"]
    requested = application.get("requestedPermissions") or []
    perm_text = _format_permission_keys(requested)
    return (
        f"### 管理员申请\n\n"
        f"- **申请人**：{name}\n"
        f"- **staffId**：`{staff_id}`\n"
        f"- **申请码**：`{token}`\n"
        f"- **申请权限**：{perm_text}\n\n"
        f"请点 **同意开放** 按上述权限授予，或 **暂不开放** 拒绝（不可修改申请权限）。\n"
        f"也可回复：**同意管理员申请 {token}** / **拒绝管理员申请 {token}**"
    )


def _notify_super_admins(
    application: dict[str, Any],
    *,
    client: Any | None = None,
) -> None:
    from web_admin_grants import list_super_admin_staff_ids  # noqa: WPS433

    notify_ids = list_super_admin_staff_ids()
    if not notify_ids:
        raise RuntimeError("未找到超级管理员")

    token = application["token"]
    approve_cmd = f"同意管理员申请 {token}"
    reject_cmd = f"拒绝管理员申请 {token}"
    body = _build_apply_card_body(application)
    applicant_id = application["staffId"]

    if str(GATEWAY_DIR) not in sys.path:
        sys.path.insert(0, str(GATEWAY_DIR))
    from dingtalk_private_message import send_robot_private_action_card2  # noqa: WPS433

    errors: list[str] = []
    targets = [aid for aid in notify_ids if aid != applicant_id]
    for admin_id in targets:
        try:
            send_robot_private_action_card2(
                admin_id,
                title="Web Agent 管理员申请",
                text=body,
                action_title1="同意开放",
                action_url1=_dtmd_robot_message(approve_cmd),
                action_title2="暂不开放",
                action_url2=_dtmd_robot_message(reject_cmd),
                client=client,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("管理员申请卡片通知失败 admin=%s", admin_id[:12])
            errors.append(str(exc))
    if targets and len(errors) == len(targets):
        raise RuntimeError(errors[0] if errors else "钉钉通知发送失败")


def _notify_applicant(staff_id: str, *, approved: bool, client: Any | None = None) -> None:
    if str(GATEWAY_DIR) not in sys.path:
        sys.path.insert(0, str(GATEWAY_DIR))
    from dingtalk_private_message import send_robot_private_text  # noqa: WPS433

    if approved:
        text = (
            "你的 Web Agent 管理员申请已通过。\n"
            "请刷新网页后即可使用管理员能力。"
        )
    else:
        text = "你的 Web Agent 管理员申请未通过，如有疑问请联系超级管理员。"
    try:
        send_robot_private_text(staff_id, text, client=client)
    except Exception as exc:  # noqa: BLE001
        logger.warning("申请人结果通知失败 staff=%s: %s", staff_id[:12], exc)


def submit_application(
    *,
    staff_id: str,
    display_name: str = "",
    requested_permissions: list[str] | None = None,
    client: Any | None = None,
    path: Path | None = None,
    applications_path: Path | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """提交管理员申请：创建 pending 记录并发送超管卡片。返回 (result, error)。"""
    is_allowed = _gateway_import()
    uid = (staff_id or "").strip()
    if not uid:
        return None, "无法识别登录身份"
    if uid.startswith("guest_"):
        return None, "访客无法申请管理员，请使用钉钉账号登录"
    if is_allowed(sender_staff_id=uid, sender_id=None):
        return None, "你已是管理员"

    name = (display_name or "").strip() or uid
    apps_path = applications_path or APPLICATIONS_PATH
    requested = _normalize_applicant_permission_keys(requested_permissions or [])
    pending = find_pending_for_staff(uid, path=apps_path)
    if pending:
        if requested_permissions is not None:
            data = _load_applications(apps_path)
            updated_pending: dict[str, Any] | None = None
            new_apps: list[dict[str, Any]] = []
            for raw in data.get("applications", []):
                item = _normalize_application(raw)
                if not item:
                    continue
                if item["token"] == pending["token"] and item["status"] == "pending":
                    item["requestedPermissions"] = requested
                    updated_pending = item
                new_apps.append(item)
            if updated_pending is not None:
                _save_applications({"applications": new_apps}, path=apps_path)
                pending = updated_pending
        return {
            "notified": False,
            "pending": True,
            "token": pending["token"],
            "requestedPermissions": pending.get("requestedPermissions") or [],
        }, None

    if _recently_notified(uid, path=path):
        logger.info("管理员申请通知跳过（本自然日已发） staff=%s", uid[:12])
        append_admin_audit_entry(
            action="apply_admin",
            operator_staff_id=uid,
            operator_display_name=name,
            target_staff_id=uid,
            target_display_name=name,
            detail="本自然日内重复申请",
        )
        return {"notified": False, "skippedDuplicate": True}, None

    data = _load_applications(apps_path)
    apps = [_normalize_application(x) for x in data.get("applications", [])]
    apps = [x for x in apps if x is not None]
    existing_tokens = {str(x["token"]) for x in apps}
    now_iso = _utc_now_iso()
    application = {
        "token": _new_token(existing_tokens),
        "staffId": uid,
        "displayName": name,
        "status": "pending",
        "createdAt": now_iso,
        "resolvedAt": "",
        "resolvedBy": "",
        "requestedPermissions": requested,
        "grantedPermissions": [],
    }
    _supersede_other_pending(
        apps,
        staff_id=uid,
        keep_token=application["token"],
        now_iso=now_iso,
    )
    apps.append(application)
    _save_applications({"applications": apps}, path=apps_path)

    try:
        _notify_super_admins(application, client=client)
    except Exception as exc:  # noqa: BLE001
        logger.exception("管理员申请钉钉通知失败 staff=%s", uid[:12])
        return application, f"申请已记录，但钉钉通知失败：{exc}"

    _record_notification(uid, path=path)
    append_admin_audit_entry(
        action="apply_admin",
        operator_staff_id=uid,
        operator_display_name=name,
        target_staff_id=uid,
        target_display_name=name,
        detail=(
            f"已通知超级管理员（申请码 {application['token']}，"
            f"权限：{_format_permission_keys(requested)}）"
        ),
    )
    logger.info(
        "管理员申请已通知超管 staff=%s token=%s",
        uid[:12],
        application["token"],
    )
    return {"notified": True, "token": application["token"]}, None


def resolve_application(
    *,
    token: str,
    approver_staff_id: str,
    approve: bool,
    client: Any | None = None,
    path: Path | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """审批管理员申请。返回 (application, error)。"""
    from web_admin_manage import (  # noqa: WPS433
        can_manage_admin_roles,
        lookup_target_display_name,
        set_admin_permissions,
        set_admin_role,
    )

    approver = (approver_staff_id or "").strip()
    if not approver:
        return None, "无法识别审批人身份"
    approver_name = lookup_target_display_name(approver) or approver
    if not can_manage_admin_roles(staff_id=approver, display_name=approver_name):
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
            if approve:
                perm_keys = list(app.get("requestedPermissions") or [])
                item["grantedPermissions"] = _normalize_applicant_permission_keys(perm_keys)
            updated = item
        new_apps.append(item)
    if updated is None:
        return None, "申请记录异常"

    if approve:
        _, err = set_admin_role(
            operator_staff_id=approver,
            operator_display_name=approver_name,
            target_staff_id=updated["staffId"],
            is_admin=True,
        )
        if err:
            return None, err
        is_allowed = _gateway_import()
        if not is_allowed(sender_staff_id=updated["staffId"], sender_id=None):
            return None, "授予管理员失败：未能写入白名单，请重试或联系超管"
        perm_map = _permissions_dict_from_keys(updated.get("grantedPermissions") or [])
        _, perm_err = set_admin_permissions(
            operator_staff_id=approver,
            operator_display_name=approver_name,
            target_staff_id=updated["staffId"],
            permissions=perm_map,
        )
        if perm_err:
            return None, perm_err

    _save_applications({"applications": new_apps}, path=path)
    _notify_applicant(updated["staffId"], approved=approve, client=client)
    append_admin_audit_entry(
        action="grant_admin" if approve else "apply_admin",
        operator_staff_id=approver,
        operator_display_name=approver_name,
        target_staff_id=updated["staffId"],
        target_display_name=updated.get("displayName") or updated["staffId"],
        detail=(
            f"钉钉审批通过，权限：{_format_permission_keys(updated.get('grantedPermissions') or [])}"
            if approve
            else "钉钉卡片/口令审批拒绝"
        ),
    )
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
