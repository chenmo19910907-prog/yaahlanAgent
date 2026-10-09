"""Admin 执行后写入 Web Agent 操作记录（失败静默）。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _ensure_web_agent_path() -> None:
    repo = Path(__file__).resolve().parents[2]
    web_agent = repo / "platform" / "web_agent"
    path = str(web_agent)
    if path not in sys.path:
        sys.path.insert(0, path)


def _parse_body(raw: bytes | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _admin_call_meta(url: str, body: dict[str, Any], *, http_method: str) -> tuple[str, str, str, str]:
    path = urlparse(url).path or url
    uid = str(body.get("userId") or body.get("uid") or body.get("momoid") or "").strip()
    phone = str(body.get("phone") or body.get("mobile") or "").strip()
    family_id = str(body.get("familyId") or "").strip()

    if "queryUserDetail" in path and uid:
        operation = f"Admin 查询用户 {uid} 详情"
        account = uid
        params = f"userId={uid}"
    elif "queryDeviceHistoryUsers" in path or "historyDevice" in path.lower():
        mmuid = str(body.get("mmuidv3") or body.get("mmuid") or "").strip()
        operation = "Admin 查询设备历史登录用户"
        account = mmuid[:32] + "..." if len(mmuid) > 32 else mmuid
        params = f"mmuidv3={mmuid}" if body.get("mmuidv3") else f"mmuid={mmuid}"
    elif "queryUserHistoryDevices" in path and uid:
        operation = f"Admin 查询用户 {uid} 历史设备"
        account = uid
        params = f"userId={uid}"
    elif "addFamilyMember" in path or "add_family" in path.lower():
        operation = f"Admin 家族添加成员 userId={uid or '?'}"
        account = uid or family_id
        params = f"userId={uid}，familyId={family_id}".strip("，")
    elif "resetCustomGift" in path or "custom_gift" in path.lower():
        operation = f"Admin 重置用户 {uid} 定制礼物上传"
        account = uid
        params = f"userId={uid}"
    else:
        operation = f"Admin {path}"
        account = uid or phone or family_id
        parts = [f"{k}={v}" for k, v in list(body.items())[:4] if v is not None]
        params = "，".join(parts)[:240]

    return operation, account, params, path


def try_record_admin_call(
    url: str,
    body: bytes | None,
    response: dict[str, Any],
    *,
    http_method: str = "POST",
    auth: str = "yaahlan",
) -> None:
    if os.environ.get("MOA_CALL_LOG_DISABLE", "").strip().lower() in ("1", "true", "yes"):
        return
    if not os.environ.get("WEB_AGENT_RUN_ID", "").strip():
        return
    if not isinstance(response, dict):
        return
    try:
        _ensure_web_agent_path()
        from web_moa_call_log import record_tool_call

        payload = _parse_body(body)
        operation, account, params, path = _admin_call_meta(url, payload, http_method=http_method)
        online = auth == "yaahlan_online" or os.environ.get("ONLINE_ENV", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        record_tool_call(
            source="admin",
            response=response,
            operation=operation,
            account_summary=account,
            service_url=path,
            method=http_method.upper() or "POST",
            params_summary=params,
            interface_display=f"Admin · {http_method.upper()} {path}",
            batch_key=os.environ.get("WEB_AGENT_BATCH_KEY", "").strip(),
            run_id=os.environ.get("WEB_AGENT_RUN_ID", "").strip(),
            operator_staff_id=os.environ.get("WEB_AGENT_CALLER_STAFF_ID", "").strip(),
            operator_name=os.environ.get("WEB_AGENT_CALLER_NAME", "").strip(),
            environment="online" if online else "test",
        )
    except Exception:  # noqa: BLE001
        return
