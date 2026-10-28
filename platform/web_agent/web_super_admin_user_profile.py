"""会话内用户资料卡（全员可查看；超管可发钉钉私聊）。"""

from __future__ import annotations

import json
import logging
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

logger = logging.getLogger("web-agent")

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

MAX_DINGTALK_MESSAGE_LEN = 4000
_PROFILE_CARD_CACHE_TTL_S = 90.0
_dingtalk_detail_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_session_usage_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _require_logged_in(staff_id: str) -> str | None:
    uid = (staff_id or "").strip()
    if not uid:
        return "未登录"
    return None


def _require_super_admin(staff_id: str) -> str | None:
    from web_admin_grants import is_super_admin

    err = _require_logged_in(staff_id)
    if err:
        return err
    if not is_super_admin(staff_id.strip()):
        return "仅超级管理员可用"
    return None


def _is_valid_target_staff_id(staff_id: str) -> bool:
    from message_board_store import is_guest_staff_id

    uid = (staff_id or "").strip()
    if not uid or is_guest_staff_id(uid):
        return False
    if uid in ("demo",):
        return False
    return True


def _fetch_dingtalk_user_detail(staff_id: str) -> dict[str, Any]:
    """topapi/v2/user/get 详情（失败返回空 dict）。"""
    uid = (staff_id or "").strip()
    if not uid:
        return {}
    try:
        from dingtalk_user_profile import _get_access_token  # noqa: WPS433

        token = _get_access_token()
    except Exception as exc:  # noqa: BLE001
        logger.debug("用户详情 token 失败 uid=%s: %s", uid[:12], exc)
        return {}

    url = f"https://oapi.dingtalk.com/topapi/v2/user/get?access_token={token}"
    payload = json.dumps({"userid": uid, "language": "zh_CN"}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
        logger.debug("用户详情查询失败 uid=%s: %s", uid[:12], exc)
        return {}
    if int(data.get("errcode") or 0) != 0:
        return {}
    result = data.get("result")
    return dict(result) if isinstance(result, dict) else {}


def _dingtalk_user_detail_cached(staff_id: str) -> dict[str, Any]:
    uid = (staff_id or "").strip()
    if not uid:
        return {}
    now = time.monotonic()
    hit = _dingtalk_detail_cache.get(uid)
    if hit and now - hit[0] < _PROFILE_CARD_CACHE_TTL_S:
        return dict(hit[1])
    detail = _fetch_dingtalk_user_detail(uid)
    _dingtalk_detail_cache[uid] = (now, detail)
    return detail


def _session_usage_stats(staff_id: str) -> dict[str, Any]:
    from web_session_store import get_session_store

    uid = (staff_id or "").strip()
    now = time.monotonic()
    hit = _session_usage_cache.get(uid)
    if hit and now - hit[0] < _PROFILE_CARD_CACHE_TTL_S:
        return dict(hit[1])

    owned = 0
    last_active = ""
    store = get_session_store()
    for meta in store.list_sessions(enrich_names=False):
        owner = (meta.web_owner_id or meta.dingtalk_owner_id or "").strip()
        updated = (meta.updated_at or "").strip()
        if owner == uid:
            owned += 1
            if updated > last_active:
                last_active = updated
            continue
        collab_ids = meta.web_collaborator_ids or []
        if uid and uid in [str(x or "").strip() for x in collab_ids]:
            if updated > last_active:
                last_active = updated
    usage = {
        "ownedSessionCount": owned,
        "lastActiveAt": last_active,
    }
    _session_usage_cache[uid] = (now, usage)
    return usage


def _admin_role_payload(staff_id: str) -> dict[str, Any]:
    from code_modify_permission import load_code_modify_allowlist
    from web_admin_grants import get_admin_permission_map, is_super_admin
    from web_admin_manage import _localhost_admin_staff_id, is_protected_admin_account
    from web_admin_permission import is_web_admin

    uid = (staff_id or "").strip()
    cfg = load_code_modify_allowlist()
    localhost_admin = _localhost_admin_staff_id()
    is_admin = uid == localhost_admin or uid in cfg.allowed_staff_ids
    protected = is_protected_admin_account(uid)
    super_admin = is_super_admin(uid) if is_admin else False
    role = "super_admin" if super_admin else ("admin" if is_admin else "user")
    role_label = {"super_admin": "超级管理员", "admin": "管理员", "user": "普通用户"}.get(
        role, "普通用户"
    )
    perms = (
        get_admin_permission_map(staff_id=uid, is_admin=is_admin, protected=protected)
        if is_admin
        else {}
    )
    enabled_perm_labels: list[str] = []
    if is_admin:
        try:
            from web_admin_grants import PERMISSION_DEFS

            label_map = {item["key"]: item["label"] for item in PERMISSION_DEFS}
        except Exception:  # noqa: BLE001
            label_map = {}
        for key, enabled in sorted(perms.items()):
            if enabled is True and key != "super_admin":
                enabled_perm_labels.append(label_map.get(key, key))
    apply_status: dict[str, Any] = {"status": "none"}
    if not is_admin:
        from web_admin_apply import application_status_for_staff

        apply_status = application_status_for_staff(uid)
    return {
        "role": role,
        "roleLabel": role_label,
        "isAdmin": is_admin,
        "isSuperAdmin": super_admin,
        "protected": protected,
        "permissionLabels": enabled_perm_labels,
        "adminApplyStatus": apply_status,
    }


_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _format_detail_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (list, tuple)):
        parts = [str(x).strip() for x in value if str(x).strip()]
        return "、".join(parts)
    return str(value).strip()


def _format_hired_date(value: Any) -> str:
    if value is None or value == "":
        return ""
    ms: int | None = None
    if isinstance(value, (int, float)):
        ms = int(value)
    else:
        s = str(value).strip()
        if s.isdigit():
            ms = int(s)
        elif s:
            return s
    if ms is None or ms <= 0:
        return ""
    dt = datetime.fromtimestamp(ms / 1000, tz=_SHANGHAI)
    return dt.strftime("%Y-%m-%d")


def _format_account_status(value: Any) -> str:
    if isinstance(value, bool):
        return "正常" if value else "未激活"
    if value in (1, "1", "true", "True"):
        return "正常"
    if value in (0, "0", "false", "False"):
        return "未激活"
    return _format_detail_value(value)


_EMPTY_DISPLAY = "—"


def _pick_detail(
    detail: dict[str, Any],
    key: str,
    *,
    alt_keys: tuple[str, ...] = (),
    formatter: Callable[[Any], str] | None = None,
) -> str:
    for k in (key, *alt_keys):
        if k not in detail:
            continue
        raw = detail.get(k)
        if raw in (None, "", []):
            continue
        return (formatter or _format_detail_value)(raw)
    return ""


def _format_admin_apply_status(apply: dict[str, Any]) -> str:
    status = str(apply.get("status") or "none").strip()
    if status == "approved":
        return "已通过"
    if status == "pending":
        token = str(apply.get("token") or "").strip()
        return f"待审批（{token}）" if token else "待审批"
    return "无"


def _analytics_usage_rows(staff_id: str) -> list[tuple[str, str]]:
    from analytics_store import get_analytics_store

    summary = get_analytics_store().summarize_user_usage(staff_id)
    label = str(summary.get("rangeLabel") or "").strip()
    requests = int(summary.get("requests") or 0)
    tokens = int(summary.get("tokens") or 0)
    src = str(summary.get("tokensSource") or "none").strip()
    req_text = f"{requests} 次" + (f"（{label}）" if label else "")
    token_note = {"recorded": "统计", "estimated": "估算"}.get(src, "")
    token_text = str(tokens) if tokens > 0 else ""
    if token_text and token_note:
        token_text = f"{token_text}（{token_note}）"
    if token_text and label:
        token_text = f"{token_text} · {label}"
    return [("Web 提问次数", req_text), ("Token 用量", token_text)]


def _build_profile_card_rows(
    *,
    detail: dict[str, Any],
    role_payload: dict[str, Any],
    usage: dict[str, Any],
    staff_id: str,
    viewer_is_super: bool,
) -> list[dict[str, str]]:
    rows: list[tuple[str, str, bool]] = []

    def slot(label: str, value: str, *, super_only: bool = False) -> None:
        rows.append((label, value, super_only))

    perm_labels = role_payload.get("permissionLabels") or []
    slot(
        "管理员权限",
        "、".join(str(x) for x in perm_labels if str(x).strip()) if perm_labels else "",
    )

    if not role_payload.get("isAdmin"):
        apply_text = _format_admin_apply_status(role_payload.get("adminApplyStatus") or {})
        if apply_text and apply_text != "无":
            slot("管理员申请", apply_text)

    slot("自有会话", str(int(usage.get("ownedSessionCount") or 0)))
    last_active = str(usage.get("lastActiveAt") or "").strip()
    slot("最近活跃", last_active)

    for label, value in _analytics_usage_rows(staff_id):
        if label == "Token 用量":
            continue
        slot(label, value)

    slot("账号状态", _pick_detail(detail, "active", formatter=_format_account_status))
    slot("邮箱", _pick_detail(detail, "email", alt_keys=("org_email",)))
    slot("办公地点", _pick_detail(detail, "work_place"))
    slot("工号", _pick_detail(detail, "job_number"))
    slot("入职日期", _pick_detail(detail, "hired_date", formatter=_format_hired_date), super_only=True)

    out: list[dict[str, str]] = []
    for label, value, super_only in rows:
        if super_only and not viewer_is_super:
            continue
        text = (value or "").strip()
        if viewer_is_super:
            display = text or _EMPTY_DISPLAY
        elif not text:
            continue
        else:
            display = text
        out.append({"label": label, "value": display})
    return out


def get_user_profile_card(
    *,
    target_staff_id: str,
    viewer_staff_id: str,
    fallback_label: str = "",
) -> tuple[dict[str, Any] | None, str | None]:
    """已登录用户查看资料卡（敏感字段与发消息仅超管）。"""
    err = _require_logged_in(viewer_staff_id)
    if err:
        return None, err
    from web_admin_grants import is_super_admin

    viewer_is_super = is_super_admin(viewer_staff_id.strip())
    uid = (target_staff_id or "").strip()
    if not _is_valid_target_staff_id(uid):
        return None, "无效的用户"

    from dingtalk_user_lookup import lookup_auth_user_display_name, resolve_user_avatars
    from dingtalk_user_profile import resolve_user_profile

    display_name = lookup_auth_user_display_name(uid, fallback_label)
    profile = resolve_user_profile(uid, known_name=fallback_label or display_name, try_api=True)
    if profile.display_name and profile.display_name != uid:
        display_name = profile.display_name
    avatar_url = profile.avatar_url or resolve_user_avatars([uid], try_api=True).get(uid, "")

    detail = _dingtalk_user_detail_cached(uid)
    role_payload = _admin_role_payload(uid)
    usage = _session_usage_stats(uid)
    card_rows = _build_profile_card_rows(
        detail=detail,
        role_payload=role_payload,
        usage=usage,
        staff_id=uid,
        viewer_is_super=viewer_is_super,
    )

    card: dict[str, Any] = {
        "staffId": uid,
        "displayName": display_name,
        "avatarUrl": avatar_url,
        **role_payload,
        "cardRows": card_rows,
        "usage": usage,
        "canSendDingtalkMessage": viewer_is_super,
    }
    return card, None


def send_super_admin_dingtalk_message(
    *,
    operator_staff_id: str,
    operator_display_name: str,
    target_staff_id: str,
    message: str,
    client: Any | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """超管代发钉钉机器人私聊文本。"""
    err = _require_super_admin(operator_staff_id)
    if err:
        return None, err
    uid = (target_staff_id or "").strip()
    if not _is_valid_target_staff_id(uid):
        return None, "无效的用户"
    body = (message or "").strip()
    if not body:
        return None, "消息不能为空"
    if len(body) > MAX_DINGTALK_MESSAGE_LEN:
        return None, f"消息过长（最多 {MAX_DINGTALK_MESSAGE_LEN} 字）"

    operator = (operator_display_name or "").strip() or "超级管理员"
    full_text = f"【Web Agent · 超管 {operator}】\n{body}"

    from dingtalk_private_message import send_robot_private_text  # noqa: WPS433

    try:
        send_robot_private_text(uid, full_text, client=client)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "超管私聊失败 operator=%s target=%s: %s",
            operator_staff_id[:12],
            uid[:12],
            exc,
        )
        return None, str(exc)

    sent_at = datetime.now(timezone.utc).isoformat()
    target_label = ""
    try:
        from dingtalk_user_lookup import lookup_auth_user_display_name

        target_label = lookup_auth_user_display_name(uid, "")
    except Exception:  # noqa: BLE001
        target_label = ""

    try:
        from web_super_admin_message_log import append_super_admin_message_log

        append_super_admin_message_log(
            operator_staff_id=operator_staff_id,
            operator_label=operator,
            target_staff_id=uid,
            target_label=target_label,
            message=body,
            sent_at=sent_at,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("超管私聊记录落库失败: %s", exc)

    return {
        "ok": True,
        "sentAt": sent_at,
        "targetStaffId": uid,
    }, None


def list_super_admin_dingtalk_message_log(
    *,
    viewer_staff_id: str,
    target_staff_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[dict[str, Any] | None, str | None]:
    err = _require_super_admin(viewer_staff_id)
    if err:
        return None, err
    from web_super_admin_message_log import list_super_admin_message_entries

    payload = list_super_admin_message_entries(
        limit=limit,
        offset=offset,
        target_staff_id=target_staff_id,
    )
    return {"ok": True, **payload}, None
