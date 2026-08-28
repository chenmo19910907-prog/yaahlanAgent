"""Web Agent：线上环境给账号加/升级 VIP 时，钉钉通知指定负责人。"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
REPO_ROOT = WEB_AGENT_DIR.parents[1]
# 默认通知孙晓东；可通过 ONLINE_VIP_NOTIFY_STAFF_ID 覆盖（逗号分隔多人）
DEFAULT_NOTIFY_STAFF_IDS = ("01302434415723305026",)

VIP_ACTION_RE = re.compile(
    r"(升级|加|增加|升到|提升至|改到|设置|开通).{0,16}(VIP|vip)|"
    r"(VIP|vip)\s*\d+.{0,16}(升级|加|增加|开通)|"
    r"给.{0,24}(账号|用户|号).{0,24}(加|升级|增加|开通).{0,12}(VIP|vip)|"
    r"(加|升级|增加|开通).{0,12}(VIP|vip)",
    re.I,
)
USER_ID_RE = re.compile(r"(?<!\d)(\d{6,12})(?!\d)")
VIP_LEVEL_RE = re.compile(r"(?:VIP|vip)\s*(\d+)", re.I)
# 中国大陆 11 位手机号；线上 VIP 场景里 11 位数字默认按手机号处理
MOBILE_CN_RE = re.compile(r"^1[3-9]\d{9}$")

logger = logging.getLogger("web-agent")


def _gateway_import(module: str, name: str) -> Any:
    if str(GATEWAY_DIR) not in sys.path:
        sys.path.insert(0, str(GATEWAY_DIR))
    return __import__(module, fromlist=[name]).__dict__[name]


def _web_agent_import(name: str) -> Any:
    if str(WEB_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(WEB_AGENT_DIR))
    from web_dingtalk_push import (  # noqa: WPS433
        _enhance_markdown_for_dingtalk,
        prepare_push_text,
        prepare_push_title,
    )

    return {
        "prepare_push_text": prepare_push_text,
        "prepare_push_title": prepare_push_title,
        "_enhance_markdown_for_dingtalk": _enhance_markdown_for_dingtalk,
    }[name]


def resolve_online_vip_notify_staff_ids() -> list[str]:
    raw = os.environ.get("ONLINE_VIP_NOTIFY_STAFF_ID", "").strip()
    if raw:
        ids = [part.strip() for part in raw.split(",") if part.strip()]
        if ids:
            return ids
    return list(DEFAULT_NOTIFY_STAFF_IDS)


def looks_like_online_vip_request(text: str) -> bool:
    """是否涉及线上环境给账号加/升级 VIP。"""
    t = (text or "").strip()
    if not t:
        return False
    looks_like_online_env_request = _gateway_import(
        "online_env_guard",
        "looks_like_online_env_request",
    )
    if not looks_like_online_env_request(t):
        return False
    return bool(VIP_ACTION_RE.search(t))


def _extract_account_token(text: str) -> str:
    """从消息提取主账号标识（去掉 VIP 等级数字避免误匹配）。"""
    t = (text or "").strip()
    if not t:
        return ""
    stripped = VIP_LEVEL_RE.sub("", t)
    candidates = [match.group(1) for match in USER_ID_RE.finditer(stripped)]
    if not candidates:
        candidates = [match.group(1) for match in USER_ID_RE.finditer(t)]
    return candidates[-1] if candidates else ""


def classify_account_identifier(token: str, text: str) -> str:
    """返回 phone / userId / unknown。"""
    value = (token or "").strip()
    if not value:
        return "unknown"
    msg = (text or "").strip()
    if re.search(r"(手机|手机号|\bphone\b)", msg, re.I):
        return "phone"
    if re.search(r"(userid|user\s*id|用户\s*id|用户id)", msg, re.I):
        return "userId"
    if MOBILE_CN_RE.match(value):
        return "phone"
    if len(value) == 11:
        return "phone"
    if 6 <= len(value) <= 10:
        return "userId"
    return "userId"


def parse_online_vip_request(text: str) -> dict[str, str]:
    """从用户消息解析账号标识、类型与目标 VIP 等级。"""
    t = (text or "").strip()
    token = _extract_account_token(t)
    account_type = classify_account_identifier(token, t)
    vip_level = ""
    level_match = VIP_LEVEL_RE.search(t)
    if level_match:
        vip_level = level_match.group(1)
    phone = token if account_type == "phone" else ""
    user_id = token if account_type == "userId" else ""
    return {
        "rawIdentifier": token,
        "accountType": account_type,
        "phone": phone,
        "userId": user_id,
        "vipLevel": vip_level,
    }


def _run_json(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=45,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-400:]
        raise RuntimeError(f"命令失败 {' '.join(cmd)}: {tail}")
    text = (proc.stdout or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError(f"未解析到 JSON: {text[:200]}")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise RuntimeError("JSON 不是 object")
    return payload


def _online_execute_cmd(*args: str) -> dict[str, Any]:
    online_execute = REPO_ROOT / "online" / "online_execute.py"
    if not online_execute.is_file():
        return {}
    return _run_json([sys.executable, str(online_execute), *args])


def _query_online_user_by_phone(phone: str) -> dict[str, Any]:
    value = (phone or "").strip()
    if not value:
        return {}
    return _online_execute_cmd("moa", "--query-user-by-phone", value)


def _query_online_user_summary(user_id: str) -> dict[str, Any]:
    uid = (user_id or "").strip()
    if not uid:
        return {}
    return _online_execute_cmd("admin", "--query-user-id", uid)


def resolve_online_vip_account(text: str) -> dict[str, Any]:
    """账号判断 → MOA/Admin 查询；返回解析与查询结果（发送通知前必须调用）。"""
    parsed = parse_online_vip_request(text)
    token = (parsed.get("rawIdentifier") or "").strip()
    account_type = (parsed.get("accountType") or "unknown").strip()
    result: dict[str, Any] = {
        "rawIdentifier": token,
        "accountType": account_type,
        "phone": "",
        "userId": "",
        "vipLevel": parsed.get("vipLevel", ""),
        "userSummary": {},
        "resolveError": "",
    }
    if not token:
        result["resolveError"] = "消息中未识别到账号或手机号"
        return result

    user_id = ""
    if account_type == "phone":
        result["phone"] = token
        try:
            phone_summary = _query_online_user_by_phone(token)
            if not phone_summary.get("registered"):
                result["resolveError"] = f"手机号 {token} 未注册"
            else:
                user_id = str(phone_summary.get("userId") or "").strip()
                if not user_id:
                    result["resolveError"] = f"手机号 {token} 未能解析 userId"
        except Exception as exc:  # noqa: BLE001
            result["resolveError"] = f"手机号查询失败: {exc}"
            logger.warning("线上 VIP 手机号查询失败 phone=%s: %s", token, exc)
    elif account_type == "userId":
        user_id = token
        result["userId"] = user_id
    else:
        result["resolveError"] = "未能判断账号类型（手机号或 userId）"
        return result

    if user_id:
        result["userId"] = user_id
        try:
            result["userSummary"] = _query_online_user_summary(user_id)
        except Exception as exc:  # noqa: BLE001
            if not result["resolveError"]:
                result["resolveError"] = f"用户详情查询失败: {exc}"
            logger.warning("线上 VIP Admin 查用户失败 user=%s: %s", user_id, exc)

    return result


def _resolve_requester_display_name(
    requester_staff_id: str = "",
    requester_name: str = "",
) -> str:
    """提问人对外展示名：优先姓名，不回落为 staffId 编号。"""
    staff_id = (requester_staff_id or "").strip()
    name = (requester_name or "").strip()
    if name and name != staff_id:
        return name
    if staff_id:
        from dingtalk_user_lookup import lookup_auth_user_display_name

        return lookup_auth_user_display_name(staff_id, name)
    return "未知"


def _format_user_summary(summary: dict[str, Any]) -> str:
    if not summary:
        return "（未能自动查询，请手动核对）"
    nickname = str(summary.get("nickname") or "").strip()
    current_vip = summary.get("vipLevel")
    phone = str(summary.get("fullPhone") or summary.get("phone") or "").strip()
    area = str(summary.get("area") or "").strip()
    parts: list[str] = []
    if nickname:
        parts.append(f"昵称 {nickname}")
    if current_vip not in (None, ""):
        parts.append(f"当前 VIP{current_vip}")
    if phone:
        parts.append(f"手机 {phone}")
    if area:
        parts.append(f"大区 {area}")
    return " | ".join(parts) if parts else "（已查询但字段为空）"


def build_online_vip_notify_markdown(
    *,
    message: str,
    requester_staff_id: str = "",
    requester_name: str = "",
    raw_identifier: str = "",
    account_type: str = "",
    phone: str = "",
    user_id: str = "",
    vip_level: str = "",
    user_summary: dict[str, Any] | None = None,
    resolve_error: str = "",
) -> str:
    requester = _resolve_requester_display_name(requester_staff_id, requester_name)
    raw = (raw_identifier or phone or user_id or "").strip() or "（消息中未识别）"
    acct_type = (account_type or "").strip()
    type_label = {"phone": "手机号", "userId": "userId"}.get(acct_type, acct_type or "未知")
    target_uid = (user_id or "").strip() or "（未能解析）"
    target_level = (vip_level or "").strip()
    target_level_label = f"VIP{target_level}" if target_level else "（消息中未识别）"
    user_info = _format_user_summary(dict(user_summary or {}))
    if resolve_error:
        user_info = f"{user_info}；{resolve_error}" if user_info else resolve_error
    now_local = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    lines = [
        "**线上 VIP 申请通知**",
        "",
        f"- **提问人**：{requester}",
        f"- **原始输入**：{raw}",
        f"- **账号类型**：{type_label}",
        f"- **userId**：{target_uid}",
        f"- **目标 VIP 等级**：{target_level_label}",
        f"- **用户信息**：{user_info}",
        "",
        "**原消息**",
        "",
        f"> {(message or '').strip()}",
        "",
        f"时间：{now_local}",
    ]
    return "\n".join(lines)


def online_vip_handoff_reply(
    *,
    message: str,
    requester_staff_id: str = "",
    requester_name: str = "",
) -> str:
    """线上 VIP 申请：同步通知负责人并返回给用户的消息（不执行 MOA）。"""
    text = (message or "").strip()
    if not looks_like_online_vip_request(text):
        return ""

    resolved = resolve_online_vip_account(text)
    if not (resolved.get("rawIdentifier") or "").strip():
        return (
            "**线上 VIP 申请未能提交**\n\n"
            f"{resolved.get('resolveError') or '消息中未识别到账号或手机号'}"
        )

    result = notify_online_vip_request(
        message=text,
        requester_staff_id=requester_staff_id,
        requester_name=requester_name,
        resolved=resolved,
    )
    raw = (resolved.get("rawIdentifier") or "").strip() or "（见原消息）"
    acct_type = (resolved.get("accountType") or "").strip()
    type_label = {"phone": "手机号", "userId": "userId"}.get(acct_type, acct_type or "—")
    user_id = (resolved.get("userId") or "").strip() or "（未能解析）"
    user_info = _format_user_summary(dict(resolved.get("userSummary") or {}))
    level = (resolved.get("vipLevel") or "").strip()
    level_label = f"VIP{level}" if level else "（见原消息）"

    if result.get("ok"):
        return (
            "**已提交线上 VIP 申请**\n\n"
            "Web Agent **不会**直接执行线上 VIP 操作，已钉钉通知负责人 **孙晓东** 处理，请等待人工操作。\n\n"
            f"| 项 | 值 |\n|---|---|\n"
            f"| 目标账号/手机 | {raw} |\n"
            f"| 账号类型 | {type_label} |\n"
            f"| userId | {user_id} |\n"
            f"| 用户信息 | {user_info} |\n"
            f"| 目标 VIP 等级 | {level_label} |"
        )

    err = str(result.get("error") or "通知发送失败").strip()
    return (
        "**线上 VIP 申请通知失败**\n\n"
        f"{err}\n\n"
        "请稍后重试，或直接在钉钉联系孙晓东。"
    )


def notify_online_vip_request(
    *,
    message: str,
    requester_staff_id: str = "",
    requester_name: str = "",
    client: Any | None = None,
    resolved: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """同步发送线上 VIP 申请通知；须先完成账号判断与查询（由 resolved 传入或内部解析）。"""
    text = (message or "").strip()
    if not looks_like_online_vip_request(text):
        return {"ok": False, "skipped": True, "reason": "not_online_vip_request"}

    account = dict(resolved or resolve_online_vip_account(text))
    if not (account.get("rawIdentifier") or "").strip():
        return {
            "ok": False,
            "error": account.get("resolveError") or "未识别账号",
        }

    user_id = str(account.get("userId") or "").strip()
    vip_level = str(account.get("vipLevel") or "").strip()
    user_summary = dict(account.get("userSummary") or {})

    body = build_online_vip_notify_markdown(
        message=text,
        requester_staff_id=requester_staff_id,
        requester_name=requester_name,
        raw_identifier=str(account.get("rawIdentifier") or ""),
        account_type=str(account.get("accountType") or ""),
        phone=str(account.get("phone") or ""),
        user_id=user_id,
        vip_level=vip_level,
        user_summary=user_summary,
        resolve_error=str(account.get("resolveError") or ""),
    )
    send_robot_private_markdown = _gateway_import(
        "dingtalk_private_message",
        "send_robot_private_markdown",
    )
    prepare_push_text = _web_agent_import("prepare_push_text")
    prepare_push_title = _web_agent_import("prepare_push_title")
    enhance = _web_agent_import("_enhance_markdown_for_dingtalk")

    push_body = prepare_push_text(enhance(body))
    title = prepare_push_title(push_body) or "线上 VIP 申请"

    recipients = resolve_online_vip_notify_staff_ids()
    sent: list[str] = []
    failed: list[dict[str, str]] = []
    for staff_id in recipients:
        try:
            send_robot_private_markdown(staff_id, title, push_body, client=client)
            sent.append(staff_id)
            logger.info(
                "线上 VIP 通知已发送 staff=%s… user=%s level=%s requester=%s",
                staff_id[:12],
                user_id or "?",
                vip_level or "?",
                (requester_staff_id or "")[:12],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("线上 VIP 通知发送失败 staff=%s: %s", staff_id[:12], exc)
            failed.append({"id": staff_id, "error": str(exc)})

    if not sent:
        first_err = failed[0]["error"] if failed else "发送失败"
        return {
            "ok": False,
            "failed": failed,
            "error": first_err,
        }

    return {
        "ok": True,
        "sent_count": len(sent),
        "failed_count": len(failed),
        "failed": failed,
        "userId": user_id,
        "vipLevel": vip_level,
    }


def maybe_notify_online_vip_request_async(
    *,
    message: str,
    requester_staff_id: str = "",
    requester_name: str = "",
) -> None:
    """后台线程发送通知，不阻塞 Web chat 启动。"""
    text = (message or "").strip()
    if not looks_like_online_vip_request(text):
        return

    def _worker() -> None:
        try:
            notify_online_vip_request(
                message=text,
                requester_staff_id=requester_staff_id,
                requester_name=requester_name,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("线上 VIP 通知后台任务失败: %s", exc)

    threading.Thread(
        target=_worker,
        name="online-vip-notify",
        daemon=True,
    ).start()
