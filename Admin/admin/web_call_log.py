"""Admin 执行后写入 Web Agent 操作记录（失败静默）。"""

from __future__ import annotations

import json
import os
import re
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


def _environment_from_account_summary(account: str) -> str | None:
    """按业务 userId 段推断环境（测试 100xxxxxxx / 线上 107xxxxxxx 等）。"""
    raw = (account or "").strip()
    if not raw:
        return None
    first = re.split(r"[\s、;；]", raw)[0].strip()
    if first.endswith("个账号"):
        first = raw.split("等")[0].strip() if "等" in raw else first
    match = re.match(r"^(\d{6,12})", first)
    if not match:
        return None
    uid = match.group(1)
    if uid.startswith("100") and len(uid) >= 9:
        return "test"
    if uid.startswith("107") and len(uid) >= 9:
        return "online"
    return None


def _admin_environment_from_request(url: str, *, auth: str) -> str:
    """按 Admin 请求域名判定环境；auth 仅作 URL 无法解析时的兜底。"""
    host = (urlparse(url).hostname or "").strip().lower()
    if host:
        if "yaahlan-admin.wemomo.com" in host and "alpha" not in host and "stage" not in host:
            return "online"
        if any(token in host for token in ("alpha", "stage", "test")):
            return "test"
        if host.endswith(".immomo.com") and "stage" in host:
            return "test"
    if auth == "yaahlan_online":
        return "online"
    return "test"


def _admin_call_meta(url: str, body: dict[str, Any], *, http_method: str) -> tuple[str, str, str, str]:
    _ensure_web_agent_path()
    from admin_call_labels import admin_call_meta

    return admin_call_meta(url, body, http_method=http_method)


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
    if not isinstance(response, dict):
        return
    try:
        _ensure_web_agent_path()
        from web_agent_audit_context import hydrate_audit_env_from_store, resolve_audit_context
        from web_moa_call_log import record_tool_call

        hydrate_audit_env_from_store()
        ctx = resolve_audit_context()
        if not ctx:
            return

        payload = _parse_body(body)
        operation, account, params, path = _admin_call_meta(url, payload, http_method=http_method)
        env = _admin_environment_from_request(url, auth=auth)
        acc_env = _environment_from_account_summary(account)
        if acc_env:
            env = acc_env
        record_tool_call(
            source="admin",
            response=response,
            operation=operation,
            account_summary=account,
            service_url=path,
            method=http_method.upper() or "POST",
            params_summary=params,
            interface_display=f"Admin · {http_method.upper()} {path}",
            batch_key=ctx["batch_key"],
            run_id=ctx["run_id"],
            operator_staff_id=ctx["operator_staff_id"],
            operator_name=ctx["operator_name"],
            environment=env,
        )
    except Exception:  # noqa: BLE001
        return
