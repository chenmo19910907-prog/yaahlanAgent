"""风控执行后写入 Web Agent 操作记录（失败静默）。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any


def _ensure_web_agent_path() -> None:
    repo = Path(__file__).resolve().parents[2]
    web_agent = repo / "platform" / "web_agent"
    path = str(web_agent)
    if path not in sys.path:
        sys.path.insert(0, path)


def _risk_call_meta(args: argparse.Namespace) -> tuple[str, str, str, str, str]:
    if getattr(args, "release_online_login_device", False):
        uid = (args.user_id or "").strip().split(",")[0]
        phone = (args.phone or "").strip().split(",")[0]
        target = phone or uid or "?"
        operation = f"风控 线上解除 {target} 登录设备/手机号"
        account = uid or phone
        params = f"phone={phone}，userId={uid}".strip("，")
        return operation, account, params, "release_online_login_device", "POST"

    if getattr(args, "release_test_device", False):
        asset = (args.device_asset or "").strip()
        name = (args.device_name or "").strip()
        label = asset or name or "测试机"
        operation = f"风控 解除测试机 {label} 设备风控"
        params = f"device={label}，reason={args.reason or ''}"
        return operation, label, params, "release_test_device", "POST"

    if getattr(args, "release_phone", False) or getattr(args, "release_sms_risk", False):
        phones = (args.phone or "").strip()
        kind = "短信" if getattr(args, "release_sms_risk", False) else "手机号"
        operation = f"风控 解除{kind} {phones} 风控"
        params = f"phone={phones}"
        return operation, phones.split(",")[0].strip(), params, "release_phone", "POST"

    if getattr(args, "release_device", False):
        mmuid = (args.mmuid or "").strip()
        operation = f"风控 解除设备 {mmuid.split(',')[0]} 风控"
        first = mmuid.split(",")[0].strip()
        params = f"mmuid={mmuid[:120]}"
        return operation, first, params, "release_device", "POST"

    operation = "风控 菜单加白"
    params = f"reason={getattr(args, 'reason', '') or ''}"
    return operation, "", params, "risk_menu_operate", "POST"


def try_record_risk_call(
    args: argparse.Namespace,
    results: list[dict[str, Any]],
) -> None:
    if os.environ.get("MOA_CALL_LOG_DISABLE", "").strip().lower() in ("1", "true", "yes"):
        return
    if not os.environ.get("WEB_AGENT_RUN_ID", "").strip():
        return
    if not results:
        return
    last = results[-1].get("response") if isinstance(results[-1], dict) else None
    if not isinstance(last, dict):
        return
    try:
        _ensure_web_agent_path()
        from web_moa_call_log import record_tool_call

        operation, account, params, op_id, http_method = _risk_call_meta(args)
        online = getattr(args, "release_online_login_device", False)
        record_tool_call(
            source="risk",
            response=last,
            operation=operation,
            account_summary=account,
            service_url=f"/risk/{op_id}",
            method=http_method,
            params_summary=params,
            interface_display=f"风控 · {op_id}",
            batch_key=os.environ.get("WEB_AGENT_BATCH_KEY", "").strip(),
            run_id=os.environ.get("WEB_AGENT_RUN_ID", "").strip(),
            operator_staff_id=os.environ.get("WEB_AGENT_CALLER_STAFF_ID", "").strip(),
            operator_name=os.environ.get("WEB_AGENT_CALLER_NAME", "").strip(),
            environment="online" if online else "test",
        )
    except Exception:  # noqa: BLE001
        return
