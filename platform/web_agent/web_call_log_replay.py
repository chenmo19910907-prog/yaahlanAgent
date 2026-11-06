"""操作记录：解析 registry 命令并重跑（跳过 Agent）。"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

WEB_AGENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEB_AGENT_DIR.parents[1]
_MCP_DIR = REPO_ROOT / "platform" / "mcp"
if str(_MCP_DIR) not in sys.path:
    sys.path.insert(0, str(_MCP_DIR))

from catalog import (  # noqa: E402
    Capability,
    build_capability_argv,
    extract_parameters,
    load_catalog,
)
from runner import run_argv  # noqa: E402

from admin_call_labels import _admin_operation_name_for_path  # noqa: E402
from web_agent_audit_context import (  # noqa: E402
    BATCH_KEY_ENV,
    CALLER_NAME_ENV,
    CALLER_STAFF_ENV,
    RUN_ID_ENV,
)
from web_moa_call_log import (  # noqa: E402
    _clean_user_id_token,
    _load_entries,
    _lookup_moa_template_url_method,
    _method_operation_name,
    _parse_param_labels_from_description,
    _parse_params_summary,
    _primary_user_id,
    collapse_batch_params_summary,
    format_operation_display,
    format_moa_interface_display,
    record_tool_call,
)

_PROMPT_PLACEHOLDER_RE = re.compile(r"<([^>|]+)(?:\|([^>]+))?>")

_TEMPLATE_JSON_RE = re.compile(r"MOA/templates/([^`\s]+\.json)")
_METHOD_IN_COMMAND_RE = re.compile(r"--method\s+(\S+)")


def _module_id_for_entry(entry: dict[str, Any]) -> str:
    env = str(entry.get("environment") or "test").strip().lower()
    if env == "online":
        return "online"
    src = str(entry.get("source") or "moa").strip().lower()
    return {"moa": "moa", "admin": "admin", "risk": "risk"}.get(src, "")


def _capabilities_for_module(module_id: str) -> list[Capability]:
    _, caps = load_catalog()
    return [c for c in caps.values() if c.module_id == module_id]


def _capability_matches_method(cap: Capability, method: str) -> bool:
    meth = (method or "").strip()
    if not meth:
        return False
    command = cap.command or ""
    if _METHOD_IN_COMMAND_RE.search(command):
        for m in _METHOD_IN_COMMAND_RE.finditer(command):
            if m.group(1).strip() == meth:
                return True
    tpl_m = _TEMPLATE_JSON_RE.search(command)
    if tpl_m:
        _, tpl_method = _lookup_moa_template_url_method(tpl_m.group(1))
        if tpl_method == meth:
            return True
    desc = cap.description or ""
    return bool(re.search(rf"(?<![\w.-]){re.escape(meth)}(?![\w.-])", desc))


def _disambiguate(matches: list[Capability], entry: dict[str, Any]) -> Capability | None:
    svc = str(entry.get("serviceUrl") or "")
    meth = str(entry.get("method") or "")
    if svc or meth:
        narrowed = [
            c
            for c in matches
            if (not svc or svc in c.command) and (not meth or meth in c.command)
        ]
        if len(narrowed) == 1:
            return narrowed[0]
    return matches[0] if len(matches) == 1 else None


def find_capability_for_entry(entry: dict[str, Any]) -> Capability | None:
    mod_id = _module_id_for_entry(entry)
    if not mod_id:
        return None
    caps = _capabilities_for_module(mod_id)
    if not caps:
        return None

    op = str(entry.get("operation") or "").strip()
    meth = str(entry.get("method") or "").strip()
    names: list[str] = []
    if op:
        names.append(op)
    if meth:
        reg_name = _method_operation_name(meth)
        if reg_name and reg_name not in names:
            names.append(reg_name)
    if mod_id == "admin":
        path_name = _admin_operation_name_for_path(str(entry.get("serviceUrl") or ""))
        if path_name and path_name not in names:
            names.insert(0, path_name)

    for name in names:
        matches = [c for c in caps if c.name == name]
        if matches:
            picked = _disambiguate(matches, entry)
            if picked:
                return picked

    svc = str(entry.get("serviceUrl") or "").strip()
    if svc and meth:
        url_matches = [c for c in caps if svc in c.command and meth in c.command]
        if len(url_matches) == 1:
            return url_matches[0]
        if url_matches:
            return _disambiguate(url_matches, entry)
    if meth:
        method_matches = [c for c in caps if _capability_matches_method(c, meth)]
        if method_matches:
            picked = _disambiguate(method_matches, entry)
            if picked:
                return picked
    return None


def _raw_params_from_entry(entry: dict[str, Any]) -> dict[str, str]:
    """重跑只取首个账号：批量/多段 paramsSummary 折叠为单账号参数。"""
    params_summary = str(entry.get("paramsSummary") or "")
    account = str(entry.get("accountSummary") or "").strip()
    method = str(entry.get("method") or "")
    call_count = max(int(entry.get("callCount") or 1), 1)
    if call_count > 1:
        params_summary = collapse_batch_params_summary(
            params_summary,
            method=method,
            call_count=call_count,
            account_summary=account,
        )
    raw = dict(_parse_params_summary(params_summary))
    uid = _primary_user_id(params=raw, account_summary=account)
    if not uid and raw.get("1"):
        uid = _clean_user_id_token(str(raw.get("1") or ""))
    if uid:
        raw["userId"] = uid
        if raw.get("1") and _clean_user_id_token(str(raw["1"])) == uid:
            raw.pop("1", None)
    return raw


def _canonical_param_key(name: str) -> str:
    return (name or "").split("|")[0].strip()


def _capability_param_maps(
    cap: Capability,
) -> tuple[dict[str, str], dict[str, str]]:
    """别名 → registry 占位主键；占位主键 → 展示标签（中文等）。"""
    alias_to_canon: dict[str, str] = {}
    canon_to_label: dict[str, str] = {}
    placeholders = extract_parameters(cap.command)
    for ph in placeholders:
        keys = [k.strip() for k in ph.split("|") if k.strip()]
        if not keys:
            continue
        canon = keys[0]
        for k in keys:
            alias_to_canon[k] = canon

    for prompt in cap.prompts or []:
        for match in _PROMPT_PLACEHOLDER_RE.finditer(str(prompt)):
            key = match.group(1).strip()
            label = (match.group(2) or "").strip()
            if not key:
                continue
            canon = _canonical_param_key(key)
            alias_to_canon[key] = canon
            alias_to_canon[canon] = canon
            if label and label != canon:
                alias_to_canon[label] = canon
                canon_to_label.setdefault(canon, label)

    desc_labels = _parse_param_labels_from_description(cap.description or "")
    for idx, label in enumerate(desc_labels):
        label = label.strip()
        if not label or idx >= len(placeholders):
            continue
        canon = _canonical_param_key(placeholders[idx])
        alias_to_canon[label] = canon
        if label != canon:
            canon_to_label.setdefault(canon, label)

    return alias_to_canon, canon_to_label


def _normalize_raw_params(raw: dict[str, str], cap: Capability | None) -> dict[str, str]:
    if not cap:
        return dict(raw)
    alias_to_canon, _ = _capability_param_maps(cap)
    out: dict[str, str] = {}
    for key, val in raw.items():
        k = str(key or "").strip()
        v = str(val if val is not None else "").strip()
        if not k:
            continue
        canon = alias_to_canon.get(k, _canonical_param_key(k))
        if v and not out.get(canon):
            out[canon] = v
        elif v:
            out[canon] = v
    return out


def _lookup_param_value(
    raw: dict[str, str],
    ph: str,
    alias_to_canon: dict[str, str],
) -> str:
    keys = [k.strip() for k in ph.split("|") if k.strip()]
    for k in keys:
        if raw.get(k):
            return raw[k]
    canon = keys[0] if keys else _canonical_param_key(ph)
    for key, val in raw.items():
        if not val:
            continue
        if alias_to_canon.get(key.strip()) == canon:
            return val
    if "userId" in keys:
        return raw.get("userId") or raw.get("userid") or raw.get("momoId") or ""
    return ""


def _merged_replay_params(
    entry: dict[str, Any],
    cap: Capability | None,
    params_rows: list[dict[str, Any]],
) -> dict[str, str]:
    base = _normalize_raw_params(_raw_params_from_entry(entry), cap)
    edited = _params_dict_from_rows(params_rows)
    for key, val in edited.items():
        if val.strip():
            base[key] = val
    return base


def params_rows_for_entry(entry: dict[str, Any], cap: Capability | None) -> list[dict[str, str]]:
    raw = _normalize_raw_params(_raw_params_from_entry(entry), cap)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    if cap:
        alias_to_canon, canon_to_label = _capability_param_maps(cap)
        for ph in extract_parameters(cap.command):
            keys = [k.strip() for k in ph.split("|") if k.strip()]
            val = _lookup_param_value(raw, ph, alias_to_canon)
            row_key = keys[0] if keys else _canonical_param_key(ph)
            if row_key in seen:
                continue
            seen.add(row_key)
            label = canon_to_label.get(row_key) or row_key
            rows.append(
                {
                    "key": row_key,
                    "label": label,
                    "value": val,
                    "placeholder": ph,
                    "editable": True,
                }
            )
        return rows

    for key, val in raw.items():
        if key in seen:
            continue
        seen.add(key)
        rows.append({"key": key, "label": key, "value": val, "placeholder": "", "editable": True})
    return rows


def _params_dict_from_rows(rows: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip()
        val = str(row.get("value") if row.get("value") is not None else "").strip()
        if key:
            out[key] = val
    return out


def _build_substitute_params(cap: Capability, raw: dict[str, str]) -> dict[str, str]:
    normalized = _normalize_raw_params(raw, cap)
    alias_to_canon, _ = _capability_param_maps(cap)
    out: dict[str, str] = {}
    for ph in extract_parameters(cap.command):
        val = _lookup_param_value(normalized, ph, alias_to_canon)
        if not val and "userId" in ph:
            val = normalized.get("thirdUid") or ""
        if not val:
            keys = [k.strip() for k in ph.split("|") if k.strip()]
            raise ValueError(f"缺少参数：{keys[0] if keys else ph}")
        out[ph] = val
    return out


def _subprocess_env_for_audit(
    *,
    batch_key: str,
    run_id: str,
    operator_staff_id: str,
    operator_name: str,
) -> dict[str, str]:
    env = os.environ.copy()
    env[BATCH_KEY_ENV] = batch_key
    env[RUN_ID_ENV] = run_id
    env[CALLER_STAFF_ENV] = operator_staff_id
    env[CALLER_NAME_ENV] = operator_name
    return env


def _format_replay_params_summary(
    raw: dict[str, str],
    cap: Capability | None,
    entry: dict[str, Any],
) -> str:
    if not raw:
        return str(entry.get("paramsSummary") or "")
    _, canon_to_label = _capability_param_maps(cap) if cap else ({}, {})
    parts: list[str] = []
    for key, val in raw.items():
        k = str(key or "").strip()
        v = str(val if val is not None else "").strip()
        if not k or not v:
            continue
        label = canon_to_label.get(k) or k
        parts.append(f"{label}={v}")
    return "，".join(parts) if parts else str(entry.get("paramsSummary") or "")


_RESULT_ROW_PRIORITY = (
    "userId",
    "registered",
    "fullNumber",
    "mobile",
    "areaCode",
    "balance",
    "diamondNum",
    "diamond",
    "gold",
    "roomId",
    "familyId",
    "level",
    "currentExp",
    "updatedFamilyCount",
    "ec",
    "em",
    "msg",
    "message",
)


def _scalar_display_value(value: Any, *, max_len: int = 320) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        text = value.strip()
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(value)
    text = text.strip()
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _result_rows_from_parsed(data: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if isinstance(data, dict):
        seen: set[str] = set()
        for key in _RESULT_ROW_PRIORITY:
            if key not in data:
                continue
            val = _scalar_display_value(data[key])
            if not val:
                continue
            rows.append({"label": key, "value": val})
            seen.add(key)
        for key, raw in data.items():
            k = str(key or "").strip()
            if not k or k in seen or k == "data":
                continue
            val = _scalar_display_value(raw)
            if not val:
                continue
            rows.append({"label": k, "value": val})
            if len(rows) >= 12:
                break
    elif data is not None:
        rows.append({"label": "输出", "value": _scalar_display_value(data, max_len=500)})
    return rows


def _replay_display_summary(ok: bool, rows: list[dict[str, str]], fallback: str) -> str:
    if not ok:
        return fallback
    by_label = {r["label"]: r["value"] for r in rows}
    uid = by_label.get("userId")
    if uid is not None:
        if uid and uid.lower() not in ("null", "none"):
            return f"成功 · userId={uid}"
        reg = by_label.get("registered")
        if reg == "否":
            return "成功 · 未注册"
    balance = by_label.get("balance") or by_label.get("diamondNum") or by_label.get("diamond")
    if balance:
        who = by_label.get("userId") or ""
        prefix = f"{who} " if who else ""
        return f"成功 · {prefix}余额={balance}".strip()
    if rows:
        first = rows[0]
        return f"成功 · {first['label']}={first['value']}"
    return fallback


def _build_replay_result_view(run: dict[str, Any], *, ok: bool, fallback_summary: str) -> dict[str, Any]:
    stdout = (run.get("stdout") or "").strip()
    stderr = (run.get("stderr") or "").strip()
    rows = _result_rows_from_parsed(run.get("data"))
    if not rows and stdout:
        rows = [{"label": "输出", "value": _scalar_display_value(stdout, max_len=600)}]
    if not ok and not rows:
        err = stderr or stdout
        if err:
            rows = [{"label": "错误", "value": _scalar_display_value(err, max_len=400)}]
    display_summary = _replay_display_summary(ok, rows, fallback_summary)
    return {
        "resultRows": rows,
        "displaySummary": display_summary,
        "stdoutTail": stdout[-2000:],
        "stderrTail": stderr[-2000:],
    }


def _replay_run_already_logged(run_id: str) -> bool:
    rid = (run_id or "").strip()
    if not rid:
        return False
    for item in _load_entries():
        if str(item.get("runId") or "").strip() == rid:
            return True
    return False


def _record_replay_call_log(
    *,
    entry: dict[str, Any],
    cap: Capability,
    merged_raw: dict[str, str],
    batch_key: str,
    run_id: str,
    operator_staff_id: str,
    operator_name: str,
    ok: bool,
    detail_tail: str,
) -> None:
    if _replay_run_already_logged(run_id):
        return
    src = str(entry.get("source") or "moa").strip().lower()
    env = str(entry.get("environment") or "test").strip() or "test"
    meth = str(entry.get("method") or "").strip()
    service_url = str(entry.get("serviceUrl") or "").strip()
    params_summary = _format_replay_params_summary(merged_raw, cap, entry)
    account = str(entry.get("accountSummary") or "").strip()
    uid = _primary_user_id(params=merged_raw, account_summary=account)
    if uid:
        account = uid
    op_base = (cap.name or str(entry.get("operation") or "")).strip()
    operation = format_operation_display(
        op_base,
        method=meth,
        params_summary=params_summary,
        account_summary=account,
        call_count=1,
    )
    iface = format_moa_interface_display(service_url=service_url, method=meth)
    response: dict[str, Any]
    if ok:
        response = {"ec": 200, "result": {"ec": 0}}
    elif src == "admin":
        response = {"ec": 500, "status": 1, "msg": (detail_tail or "")[:120]}
    else:
        response = {"ec": 500, "result": {"ec": -1}, "msg": (detail_tail or "")[:120]}
    record_tool_call(
        source=src,
        response=response,
        operation=operation,
        account_summary=account,
        service_url=service_url,
        method=meth,
        params_summary=params_summary,
        interface_display=iface,
        batch_key=batch_key,
        run_id=run_id,
        operator_staff_id=operator_staff_id,
        operator_name=operator_name,
        environment=env,
        record_on_failure=True,
        operation_key=f"web-replay#{run_id}",
    )


def get_entry_by_id(entry_id: str) -> dict[str, Any] | None:
    eid = str(entry_id or "").strip()
    if not eid:
        return None
    for item in _load_entries():
        if str(item.get("id") or "") == eid:
            return item
    return None


def replay_spec(entry_id: str) -> dict[str, Any]:
    entry = get_entry_by_id(entry_id)
    if entry is None:
        raise ValueError("未找到操作记录")
    cap = find_capability_for_entry(entry)
    rows = params_rows_for_entry(entry, cap)
    can_replay = cap is not None and "&&" not in (cap.command if cap else "")
    reason = ""
    if not cap:
        reason = "未匹配到工具台 registry 能力，暂不支持直接运行"
    elif "&&" in cap.command:
        reason = "该能力命令含多段 shell（&&），请在本机终端执行"
        can_replay = False

    call_count = max(int(entry.get("callCount") or 1), 1)
    replay_hint = ""
    if call_count > 1:
        replay_hint = f"原记录含 {call_count} 次调用，运行仅对首个账号执行 1 次"

    return {
        "entryId": entry_id,
        "operation": str(entry.get("operation") or ""),
        "source": str(entry.get("source") or ""),
        "environment": str(entry.get("environment") or "test"),
        "canReplay": can_replay,
        "reason": reason,
        "replayHint": replay_hint,
        "moduleId": cap.module_id if cap else "",
        "capabilityId": cap.id if cap else "",
        "capabilityName": cap.name if cap else "",
        "paramsRows": rows,
    }


def execute_replay(
    *,
    entry_id: str,
    params_rows: list[dict[str, Any]],
    operator_staff_id: str,
    operator_name: str,
    session_id: str = "",
    timeout_sec: int = 180,
) -> dict[str, Any]:
    entry = get_entry_by_id(entry_id)
    if entry is None:
        raise ValueError("未找到操作记录")
    if str(entry.get("environment") or "").strip().lower() == "online":
        from web_admin_permission import has_admin_permission

        if not has_admin_permission(staff_id=operator_staff_id, permission="online"):
            raise ValueError("线上环境运行需要管理员 online 权限")
    cap = find_capability_for_entry(entry)
    if cap is None:
        raise ValueError("未匹配到可运行能力")
    if "&&" in cap.command:
        raise ValueError("该能力不支持一键运行（多段命令）")

    raw = _merged_replay_params(entry, cap, params_rows)
    sub_params = _build_substitute_params(cap, raw)
    argv = build_capability_argv(cap.module_id, cap.id, sub_params)

    batch_key = f"web:replay:{entry_id[:12]}:{uuid.uuid4().hex[:8]}"
    run_id = uuid.uuid4().hex[:12]
    sid = str(session_id or "").strip()
    if sid:
        batch_key = f"web:{sid}"

    try:
        from web_agent_audit_context import publish_audit_context

        publish_audit_context(
            batch_key=batch_key,
            run_id=run_id,
            operator_staff_id=operator_staff_id,
            operator_name=operator_name,
            source="web-replay",
        )
    except Exception:  # noqa: BLE001
        pass

    sub_env = _subprocess_env_for_audit(
        batch_key=batch_key,
        run_id=run_id,
        operator_staff_id=operator_staff_id,
        operator_name=operator_name,
    )
    result = run_argv(
        argv,
        timeout_sec=max(30, min(int(timeout_sec or 180), 600)),
        env=sub_env,
    )
    ok = bool(result.get("ok"))
    summary = "成功" if ok else f"失败（exit {result.get('exit_code')}）"
    tail = (result.get("stderr") or result.get("stdout") or "")[-400:]
    view = _build_replay_result_view(result, ok=ok, fallback_summary=summary)
    try:
        _record_replay_call_log(
            entry=entry,
            cap=cap,
            merged_raw=raw,
            batch_key=batch_key,
            run_id=run_id,
            operator_staff_id=operator_staff_id,
            operator_name=operator_name,
            ok=ok,
            detail_tail=tail,
        )
    except Exception:  # noqa: BLE001
        pass
    return {
        "ok": ok,
        "summary": summary,
        "displaySummary": view["displaySummary"],
        "resultRows": view["resultRows"],
        "exitCode": result.get("exit_code"),
        "argv": result.get("argv"),
        "stdoutTail": view["stdoutTail"],
        "stderrTail": view["stderrTail"],
        "detailTail": tail,
        "moduleId": cap.module_id,
        "capabilityId": cap.id,
        "capabilityName": cap.name,
    }
