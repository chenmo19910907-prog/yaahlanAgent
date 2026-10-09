"""Web Agent / 网关 MOA 调用审计：按任务内同操作合并批量记录。"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

WEB_AGENT_DIR = Path(__file__).resolve().parent
LOG_PATH = WEB_AGENT_DIR / "data" / "moa_call_log.json"
MAX_ENTRIES = 2000

BJ = timezone(timedelta(hours=8))
REPO_ROOT = WEB_AGENT_DIR.parents[1]
MOA_TEMPLATES_DIR = REPO_ROOT / "MOA" / "templates"
_USER_ID_RE = re.compile(r"\b1\d{5,8}\b")
_MOMOID_HEX_RE = re.compile(r"^[0-9a-f]{16}$")
_SERVICE_METHOD_INLINE_RE = re.compile(r"`(/service/[^`\s]+)`\s*·\s*`([^`]+)`")
_SKIP_ASSISTANT_PARAM_KEYS = frozenset(
    {
        "项目",
        "项",
        "操作",
        "环境",
        "返回",
        "接口返回",
        "结果",
        "验收查询",
        "使用的已入库能力",
    }
)
_SENSITIVE_PARAM_KEYS = frozenset({"signKey", "signkey"})
_GENERIC_PARAM_TITLE_RE = re.compile(r"^参数\d+$")
_PARAMS_IN_DESC_RE = re.compile(r"params=([^）)。\n]+)", re.I)
_METHOD_IN_DESC_RE = re.compile(r"（([a-zA-Z][\w]+)）")
_REGISTRY_PATH = REPO_ROOT / "MOA" / "config" / "registry.json"
_CLI_FLAG_LABEL: dict[str, str] = {
    "vip-user-id": "userId",
    "vip-exp": "value",
    "vip-del-user-id": "userId",
    "vip-try-user-id": "userId",
    "vip-try-level": "tryLevel",
    "vip-try-duration-seconds": "durationSeconds",
    "noble-user-id": "userId",
    "noble-exp": "value",
    "diamond-user-id": "userId",
    "diamond-num": "num",
    "user-id": "userId",
    "phone": "phone",
    "family-id": "familyId",
    "family-exp": "value",
}
_SKIP_CLI_FLAGS = frozenset(
    {
        "payload-file",
        "online",
        "level-exp-mode",
        "vip-query-current",
        "family-query-current",
        "moa-method",
    }
)
_METHOD_PARAM_LABELS_FALLBACK: dict[str, list[str]] = {
    "addVipValue": ["userId", "value"],
    "getVipInfo": ["userId"],
    "delVipInfo": ["userId"],
    "dispatchTryVip": ["userId", "tryLevel", "durationSeconds"],
    "incrNobelLevel": ["userId", "value"],
    "incrUserSendGiftDiamondsNum": ["userId", "num"],
    "incrUserReceiveGiftDiamondsNum": ["userId", "num"],
}
_METHOD_OPERATION_FALLBACK: dict[str, str] = {
    "getVipInfo": "VIP经验值-查询当前等级经验",
    "addVipValue": "VIP经验值-增加",
    "delVipInfo": "VIP等级-清除VIP信息",
    "dispatchTryVip": "VIP体验卡-下发",
}
_method_param_labels_cache: dict[str, list[str]] | None = None
_method_operation_names_cache: dict[str, str] | None = None


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso_to_bj_display(iso: str) -> str:
    raw = (iso or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BJ).strftime("%Y-%m-%d %H:%M:%S")


def _load_entries() -> list[dict[str, Any]]:
    if not LOG_PATH.is_file():
        return []
    try:
        data = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _save_entries(entries: list[dict[str, Any]]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    trimmed = entries[-MAX_ENTRIES:]
    LOG_PATH.write_text(
        json.dumps(trimmed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _resolve_operator_from_batch_key(batch_key: str) -> tuple[str, str]:
    key = (batch_key or "").strip()
    if not key.startswith("web:"):
        return "", ""
    session_id = key[4:].strip()
    if not session_id:
        return "", ""
    try:
        from web_session_store import get_session_store

        meta = get_session_store().get_session(session_id)
        if meta is None:
            return "", ""
        staff = (getattr(meta, "dingtalk_owner_id", None) or "").strip()
        name = (getattr(meta, "title", None) or "").strip()
        return staff, name
    except Exception:  # noqa: BLE001
        return "", ""


def _lookup_moa_template_url_method(template_file: str) -> tuple[str, str]:
    name = (template_file or "").strip()
    if not name:
        return "", ""
    path = MOA_TEMPLATES_DIR / name if not name.startswith("MOA/") else REPO_ROOT / name
    if not path.is_file():
        return "", ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", ""
    if not isinstance(data, dict):
        return "", ""
    return str(data.get("url") or "").strip(), str(data.get("method") or "").strip()


def _parse_param_labels_from_description(description: str) -> list[str]:
    text = (description or "").strip()
    m = _PARAMS_IN_DESC_RE.search(text)
    if not m:
        return []
    raw = m.group(1).strip()
    if raw.startswith("{") and raw.endswith("}"):
        raw = raw[1:-1].strip()
    parts = re.split(r"[,、]\s*", raw)
    labels: list[str] = []
    for piece in parts:
        label = piece.strip()
        if not label:
            continue
        label = re.sub(r"\s+(string|long|int|json|L)\b.*$", "", label, flags=re.I)
        label = label.replace("增量", "value").strip()
        if label:
            labels.append(label)
    return labels


def _parse_param_labels_from_command(command: str) -> list[str]:
    labels: list[str] = []
    for flag in re.findall(r"--([\w-]+)", command or ""):
        if flag in _SKIP_CLI_FLAGS:
            continue
        label = _CLI_FLAG_LABEL.get(flag)
        if label and label not in labels:
            labels.append(label)
    return labels


def _build_method_param_labels_index() -> dict[str, list[str]]:
    index: dict[str, list[str]] = dict(_METHOD_PARAM_LABELS_FALLBACK)
    if not _REGISTRY_PATH.is_file():
        return index
    try:
        data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return index
    caps = data.get("capabilities")
    if not isinstance(caps, list):
        return index
    for cap in caps:
        if not isinstance(cap, dict):
            continue
        desc = str(cap.get("description") or "")
        command = str(cap.get("command") or "")
        labels = _parse_param_labels_from_description(desc)
        if not labels:
            labels = _parse_param_labels_from_command(command)
        if not labels:
            continue
        methods: set[str] = set()
        for mm in _METHOD_IN_DESC_RE.findall(desc):
            methods.add(mm)
        tpl_m = re.search(r"MOA/templates/([^`\s]+\.json)", command)
        if tpl_m:
            _, tpl_method = _lookup_moa_template_url_method(tpl_m.group(1))
            if tpl_method:
                methods.add(tpl_method)
        for meth in methods:
            prev = index.get(meth)
            if prev is None or len(labels) > len(prev):
                index[meth] = labels
    return index


def _method_param_labels(method: str) -> list[str]:
    global _method_param_labels_cache
    meth = (method or "").strip()
    if not meth:
        return []
    if _method_param_labels_cache is None:
        _method_param_labels_cache = _build_method_param_labels_index()
    return list(_method_param_labels_cache.get(meth) or _METHOD_PARAM_LABELS_FALLBACK.get(meth) or [])


def _build_method_operation_names_index() -> dict[str, str]:
    index: dict[str, str] = dict(_METHOD_OPERATION_FALLBACK)
    if not _REGISTRY_PATH.is_file():
        return index
    try:
        data = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return index
    caps = data.get("capabilities")
    if not isinstance(caps, list):
        return index
    for cap in caps:
        if not isinstance(cap, dict):
            continue
        name = str(cap.get("name") or "").strip()
        if not name:
            continue
        command = str(cap.get("command") or "")
        if "--vip-query-current" in command:
            index["getVipInfo"] = name
            continue
        tpl_m = re.search(r"MOA/templates/([^`\s]+\.json)", command)
        if not tpl_m:
            continue
        _, tpl_method = _lookup_moa_template_url_method(tpl_m.group(1))
        if tpl_method and tpl_method not in index:
            index[tpl_method] = name
    return index


def _method_operation_name(method: str) -> str:
    global _method_operation_names_cache
    meth = (method or "").strip()
    if not meth:
        return ""
    if _method_operation_names_cache is None:
        _method_operation_names_cache = _build_method_operation_names_index()
    return str(_method_operation_names_cache.get(meth) or "")


def resolve_operation_display(operation: str, *, method: str) -> str:
    """按实际 MOA method 修正操作标题（如 getVipInfo 不再显示增加经验值模板名）。"""
    meth = (method or "").strip()
    if not meth:
        return (operation or "").strip() or "MOA 调用"
    named = _method_operation_name(meth)
    if named:
        return named
    return (operation or "").strip() or meth


def _parse_params_summary(params_summary: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for piece in re.split(r"[，,]", params_summary or ""):
        seg = piece.strip()
        if not seg or "=" not in seg:
            continue
        key, val = seg.split("=", 1)
        key = key.strip()
        val = val.strip()
        if key and val:
            result[key] = val
    return result


def _param_from_summary(params_summary: str, key: str) -> str:
    """从 paramsSummary 取值（含批量折叠文案「每账号 num=100（共…）」）。"""
    params = _parse_params_summary(params_summary)
    val = (params.get(key) or "").strip()
    if val:
        val = re.split(r"[（(]", val)[0].strip()
        if val:
            return val
    text = params_summary or ""
    for pattern in (
        rf"\b{re.escape(key)}=(\d+)",
        rf"每账号\s+{re.escape(key)}=(\d+)",
    ):
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return ""


def _primary_user_id(*, params: dict[str, str], account_summary: str) -> str:
    if params.get("userId"):
        return params["userId"]
    account = beautify_account_summary(account_summary)
    account = re.sub(r"^(测试|线上)\s*·\s*", "", account).strip()
    if not account:
        return ""
    head = re.split(r"[、;；]", account)[0].strip()
    m_batch = re.match(r"^(\d{6,11})\s+等\s+\d+\s*个账号$", head)
    if m_batch:
        return m_batch.group(1)
    if _USER_ID_RE.fullmatch(head):
        return head
    return ""


def _resolve_batch_account_count(*, account_summary: str, call_count: int) -> int:
    count = max(int(call_count or 1), 1)
    account = beautify_account_summary(account_summary)
    account = re.sub(r"^(测试|线上)\s*·\s*", "", account).strip()
    if not account:
        return count
    m = re.search(r"等\s*(\d+)\s*个账号", account)
    if m:
        return max(count, int(m.group(1)))
    parts = [p.strip() for p in re.split(r"[、;；]", account) if p.strip()]
    if len(parts) > 1:
        return max(count, len(parts))
    return count


def _operation_subject(*, uid: str, account_summary: str, call_count: int) -> str:
    batch_n = _resolve_batch_account_count(account_summary=account_summary, call_count=call_count)
    if batch_n <= 1:
        return f"用户 {uid}" if uid else ""
    head = uid
    if not head:
        account = beautify_account_summary(account_summary)
        account = re.sub(r"^(测试|线上)\s*·\s*", "", account).strip()
        m = re.match(r"^(\d{6,11})\s+等", account)
        if m:
            head = m.group(1)
        elif account:
            head = re.split(r"[、;；]", account)[0].strip()
    if head:
        return f"{head} 等 {batch_n} 个账号"
    return f"{batch_n} 个账号"


def build_semantic_operation_summary(
    method: str,
    params_summary: str,
    *,
    account_summary: str = "",
    call_count: int = 1,
) -> str:
    """生成可读操作描述（如「用户 100465989 增加 1 VIP经验值」）。"""
    meth = (method or "").strip()
    if not meth:
        return ""
    params = _parse_params_summary(params_summary)
    uid = _primary_user_id(params=params, account_summary=account_summary)
    phone = params.get("thirdUid") or params.get("phone") or params.get("mobile")

    if meth == "queryLoginStatusV2" and phone:
        return f"查询手机号 {phone} 对应 userId"
    subject = _operation_subject(uid=uid, account_summary=account_summary, call_count=call_count)
    batch_n = _resolve_batch_account_count(account_summary=account_summary, call_count=call_count)

    if meth == "getVipInfo" and (uid or batch_n > 1):
        if batch_n > 1:
            return f"{subject}各查询 VIP经验值"
        return f"查询用户 {uid} VIP经验值"
    if meth == "addVipValue" and (uid or batch_n > 1):
        delta = (
            _param_from_summary(params_summary, "value")
            or _param_from_summary(params_summary, "vipExp")
            or params.get("value")
            or params.get("vipExp")
            or "?"
        )
        if batch_n > 1:
            return f"{subject}各增加 {delta} VIP经验值"
        return f"用户 {uid} 增加 {delta} VIP经验值"
    if meth == "delVipInfo" and uid:
        if batch_n > 1:
            return f"{subject}各清除 VIP信息"
        return f"清除用户 {uid} VIP信息"
    if meth == "dispatchTryVip" and uid:
        level = params.get("tryLevel") or params.get("level") or "?"
        duration = params.get("durationSeconds") or params.get("duration") or "?"
        if batch_n > 1:
            return f"{subject}各下发 VIP{level} 体验 {duration} 秒"
        return f"用户 {uid} 下发 VIP{level} 体验 {duration} 秒"
    if meth == "provideDiamond" and (uid or batch_n > 1):
        num = _param_from_summary(params_summary, "num") or params.get("num") or "?"
        if batch_n > 1:
            return f"{subject}各发放 {num} 钻石"
        return f"用户 {uid} 发放 {num} 钻石"
    if meth == "incrNobelLevel" and (uid or batch_n > 1):
        delta = (
            _param_from_summary(params_summary, "value")
            or _param_from_summary(params_summary, "num")
            or params.get("value")
            or params.get("num")
            or "?"
        )
        if batch_n > 1:
            return f"{subject}各增加 {delta} 贵族经验值"
        return f"用户 {uid} 增加 {delta} 贵族经验值"
    if meth in ("incrUserSendGiftDiamondsNum", "incrUserReceiveGiftDiamondsNum") and (uid or batch_n > 1):
        num = (
            _param_from_summary(params_summary, "num")
            or _param_from_summary(params_summary, "value")
            or params.get("num")
            or params.get("value")
            or "?"
        )
        kind = "财富值" if meth == "incrUserSendGiftDiamondsNum" else "魅力值"
        if batch_n > 1:
            return f"{subject}各增加 {num} {kind}"
        return f"用户 {uid} 增加 {num} {kind}"

    if uid and params.get("num"):
        reg = _method_operation_name(meth)
        if reg and "钻石" in reg:
            if batch_n > 1:
                return f"{subject}各发放 {params['num']} 钻石"
            return f"用户 {uid} 发放 {params['num']} 钻石"

    return ""


def format_operation_display(
    operation: str,
    *,
    method: str = "",
    params_summary: str = "",
    account_summary: str = "",
    call_count: int = 1,
) -> str:
    semantic = build_semantic_operation_summary(
        method,
        params_summary,
        account_summary=account_summary,
        call_count=call_count,
    )
    if semantic:
        return semantic
    return resolve_operation_display(operation, method=method)


def _is_generic_param_key(key: str) -> bool:
    k = (key or "").strip()
    return bool(k) and k.isdigit()


def _resolve_param_item_label(item: dict[str, Any], index: int, method: str) -> str:
    title = str(item.get("title") or "").strip()
    if title and title != "0" and not _GENERIC_PARAM_TITLE_RE.match(title):
        return title
    labels = _method_param_labels(method)
    if index < len(labels):
        return labels[index]
    name = str(item.get("name") or "").strip()
    if name and not _is_generic_param_key(name):
        return name
    return name or f"arg{index + 1}"


def _looks_like_momo_id(value: str) -> bool:
    return bool(_MOMOID_HEX_RE.match((value or "").strip()))


def _environment_display_label(environment: str) -> str:
    env = (environment or "test").strip().lower()
    if env in ("online", "prod", "production"):
        return "线上"
    return "测试"


def beautify_account_summary(account_summary: str) -> str:
    """去掉 MOA payload 的 momoId（16 位 hex），仅保留业务 userId 等。"""
    raw = (account_summary or "").strip()
    if not raw:
        return raw
    parts = re.split(r"[、;；]", raw)
    kept: list[str] = []
    seen: set[str] = set()
    for piece in parts:
        seg = piece.strip()
        if not seg or _looks_like_momo_id(seg):
            continue
        if seg not in seen:
            seen.add(seg)
            kept.append(seg)
    if not kept:
        return raw.split("、")[0].split("；")[0].strip() if raw else ""
    if len(kept) == 1:
        return kept[0]
    if len(kept) <= 3:
        return "、".join(kept)
    return f"{kept[0]} 等 {len(kept)} 个账号"


def format_account_summary_display(account_summary: str, *, environment: str = "") -> str:
    """账号展示：环境 + 业务账号（不含 momoId）。"""
    account = beautify_account_summary(account_summary)
    env_label = _environment_display_label(environment)
    if not account:
        return env_label
    prefix = f"{env_label} · "
    if account.startswith("测试 · ") or account.startswith("线上 · "):
        return account
    return f"{prefix}{account}"


def beautify_params_summary(params_summary: str, *, method: str = "") -> str:
    """将 1= / 2= 等占位键替换为方法语义字段名（展示用）。"""
    raw = (params_summary or "").strip()
    if not raw or not method:
        return raw
    labels = _method_param_labels(method)
    if not labels:
        return raw
    parts: list[str] = []
    for piece in re.split(r"[，,]", raw):
        seg = piece.strip()
        if not seg or "=" not in seg:
            if seg:
                parts.append(seg)
            continue
        key, val = seg.split("=", 1)
        key = key.strip()
        val = val.strip()
        if _is_generic_param_key(key):
            idx = int(key) - 1
            if 0 <= idx < len(labels):
                key = labels[idx]
        parts.append(f"{key}={val}")
    return "，".join(parts)


def format_moa_interface_display(
    *,
    service_url: str = "",
    method: str = "",
    moa_interface: str = "",
) -> str:
    preset = (moa_interface or "").strip()
    if preset:
        return preset
    url = (service_url or "").strip()
    meth = (method or "").strip()
    if url and meth:
        return f"{url} · {meth}"
    return url or meth


def _stringify_param_value(val: Any, *, max_piece: int = 48) -> str:
    if isinstance(val, dict):
        inner: list[str] = []
        for key, item in val.items():
            if str(key) in _SENSITIVE_PARAM_KEYS:
                continue
            inner.append(f"{key}={_stringify_param_value(item, max_piece=max_piece)}")
            if len(inner) >= 8:
                break
        text = "，".join(inner)
    elif isinstance(val, list):
        text = json.dumps(val[:6], ensure_ascii=False, separators=(",", ":"))
    else:
        text = str(val)
    text = text.strip()
    if len(text) > max_piece:
        return text[: max_piece - 3] + "..."
    return text


def extract_params_summary_from_payload(
    payload: dict[str, Any],
    *,
    max_len: int = 240,
    method: str = "",
) -> str:
    meth = (method or str(payload.get("method") or "")).strip()
    params = payload.get("params")
    if not isinstance(params, list):
        momo = payload.get("momoId")
        return str(momo).strip() if momo else ""
    parts: list[str] = []
    for idx, item in enumerate(params):
        if not isinstance(item, dict):
            continue
        val = item.get("value")
        if val is None:
            val = item.get("json")
        if val is None:
            continue
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                val = parsed
            except json.JSONDecodeError:
                pass
        if isinstance(val, dict):
            for key, sub in val.items():
                if str(key) in _SENSITIVE_PARAM_KEYS:
                    continue
                parts.append(f"{key}={_stringify_param_value(sub)}")
        else:
            name = _resolve_param_item_label(item, idx, meth)
            piece = _stringify_param_value(val)
            if _is_generic_param_key(name):
                labels = _method_param_labels(meth)
                if idx < len(labels):
                    name = labels[idx]
            parts.append(f"{name}={piece}" if name else piece)
        if len(parts) >= 10:
            break
    text = "，".join(parts)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _extract_assistant_table_params(assistant_text: str) -> list[str]:
    parts: list[str] = []
    in_verify_section = False
    for line in (assistant_text or "").splitlines():
        if "验收查询" in line:
            in_verify_section = True
            continue
        if in_verify_section:
            continue
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 2:
            continue
        key = re.sub(r"[*`\s]", "", cells[0])
        if not key or key in _SKIP_ASSISTANT_PARAM_KEYS or set(key) <= {"-"}:
            continue
        if key == "接口":
            continue
        val = cells[1].strip().strip("*")
        val = re.sub(r"^`|`$", "", val)
        val = re.sub(r"\*\*", "", val).strip()
        if not val:
            continue
        if re.match(r"^ec\s*[=:]", val, re.I):
            continue
        if re.search(r"成功（历史回溯）", val):
            continue
        parts.append(f"{key}={val}")
    return parts


def extract_moa_call_details_from_assistant(
    assistant_text: str,
    *,
    max_param_len: int = 240,
) -> dict[str, str]:
    """从 Agent 回复解析 MOA 接口与参数摘要（历史回溯用）。"""
    text = assistant_text or ""
    service_url = ""
    method = ""

    m = _SERVICE_METHOD_INLINE_RE.search(text)
    if m:
        service_url, method = m.group(1).strip(), m.group(2).strip()

    if not method:
        m_iface = re.search(r"[|｜]\s*接口\s*[|｜]\s*([^|\n]+)", text, re.I)
        if m_iface:
            method = re.sub(r"[*`\s]", "", m_iface.group(1))

    tpl_m = re.search(r"MOA/templates/([^`\s]+\.json)", text)
    if tpl_m:
        tpl_url, tpl_method = _lookup_moa_template_url_method(tpl_m.group(1))
        if not service_url:
            service_url = tpl_url
        if not method:
            method = tpl_method

    op_m = re.search(r"操作\s*[|｜]\s*([^|\n]+?)\s*(?:[|｜]|$)", text, re.I)
    if op_m and not method:
        pm = re.search(r"[（(]\s*`?([^`）)\n]+)`?\s*[）)]", op_m.group(1))
        if pm:
            method = pm.group(1).strip()

    param_parts = _extract_assistant_table_params(text)
    if not param_parts:
        for flag, name in (
            (r"--diamond-user-id\s+(\S+)", "userId"),
            (r"--diamond-num\s+(\S+)", "num"),
            (r"--user-id\s+(\S+)", "userId"),
            (r"--phone\s+(\S+)", "phone"),
        ):
            m_cli = re.search(flag, text, re.I)
            if m_cli:
                param_parts.append(f"{name}={m_cli.group(1)}")

    params_summary = "，".join(param_parts)
    if len(params_summary) > max_param_len:
        params_summary = params_summary[: max_param_len - 3] + "..."

    moa_interface = format_moa_interface_display(service_url=service_url, method=method)
    return {
        "serviceUrl": service_url,
        "method": method,
        "moaInterface": moa_interface,
        "paramsSummary": params_summary,
    }


def _operation_label(*, payload_file: str, service_url: str, method: str) -> str:
    meth = (method or "").strip()
    if meth:
        by_method = _method_operation_name(meth)
        if by_method:
            return by_method
    pf = (payload_file or "").strip()
    if pf:
        stem = Path(pf).stem
        if stem:
            return stem
    svc = (service_url or "").strip()
    if svc.startswith("/service/"):
        svc = svc[len("/service/") :]
    meth = (method or "").strip() or "execute"
    if svc:
        return f"{meth} · {svc.split('/')[-1]}"
    return meth


def _extract_account_hint(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    params = payload.get("params")
    if isinstance(params, list):
        for item in params:
            if not isinstance(item, dict):
                continue
            val = item.get("value")
            if isinstance(val, str) and _USER_ID_RE.search(val):
                parts.append(val[:120])
            elif isinstance(val, dict):
                blob = json.dumps(val, ensure_ascii=False)
                ids = _USER_ID_RE.findall(blob)
                if ids:
                    parts.extend(ids[:5])
    if not parts:
        return ""
    uniq: list[str] = []
    seen: set[str] = set()
    for p in parts:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    if len(uniq) == 1:
        return uniq[0]
    if len(uniq) <= 3:
        return "、".join(uniq)
    return f"{uniq[0]} 等 {len(uniq)} 个账号"


def _result_from_response(resp: dict[str, Any]) -> tuple[bool, str]:
    ec = resp.get("ec")
    em = resp.get("em")
    try:
        ec_int = int(ec) if ec is not None else None
    except (TypeError, ValueError):
        ec_int = None
    outer_ok = ec_int in (0, 200)
    inner_ec: int | None = None
    inner = resp.get("result")
    if isinstance(inner, dict) and "ec" in inner:
        try:
            inner_ec = int(inner.get("ec"))
        except (TypeError, ValueError):
            inner_ec = None
    ok = outer_ok and (inner_ec is None or inner_ec in (0, 200))
    if ok:
        detail = "成功"
        if inner_ec is not None:
            detail = f"成功（业务 ec={inner_ec}）"
    else:
        if inner_ec is not None and inner_ec not in (0, 200):
            detail = f"失败（业务 ec={inner_ec}）"
        else:
            detail = f"失败（ec={ec_int}, {em or ''}）".strip()
    return ok, detail


_UNKNOWN_OPERATOR_NAMES = frozenset({"未知", "未知用户", "unknown"})


def _operator_name_unknown(entry: dict[str, Any]) -> bool:
    name = str(entry.get("operatorName") or "").strip()
    if not name:
        return True
    if name.lower() in _UNKNOWN_OPERATOR_NAMES:
        return True
    return name in _UNKNOWN_OPERATOR_NAMES


def prune_entries_with_unknown_operator() -> int:
    """删除调用人姓名为「未知」的记录，返回删除条数。"""
    entries = _load_entries()
    kept = [item for item in entries if not _operator_name_unknown(item)]
    removed = len(entries) - len(kept)
    if removed > 0:
        _save_entries(kept)
    return removed


def _merge_account_summary(existing: str, new: str, *, call_count: int = 0) -> str:
    old = beautify_account_summary(existing)
    add = beautify_account_summary(new)
    n = max(int(call_count or 0), 1)
    if n > 1:
        first = _primary_user_id(params={}, account_summary=old) or _primary_user_id(
            params={},
            account_summary=add,
        )
        if first:
            return f"{first} 等 {n} 个账号"
    if not add:
        return old
    if not old:
        return add
    if add in old or old.startswith(add.split(" 等")[0]):
        return old
    if "等" in old and "等" in add:
        return old
    return f"{old}、{add}"


_BATCH_PARAM_ID_KEYS = frozenset({"userId", "thirdUid", "phone", "mobile"})


def collapse_batch_params_summary(
    params_summary: str,
    *,
    method: str = "",
    call_count: int = 1,
    account_summary: str = "",
) -> str:
    """批量合并记录：只保留共性参数，不逐条拼接 userId 等。"""
    batch_n = _resolve_batch_account_count(
        account_summary=account_summary,
        call_count=call_count,
    )
    if batch_n <= 1:
        return beautify_params_summary(params_summary, method=method)
    raw = beautify_params_summary(params_summary, method=method)
    params = _parse_params_summary(raw)
    meth = (method or "").strip()
    per_account = ""
    if meth == "provideDiamond" and params.get("num"):
        per_account = f"每账号 num={params['num']}"
    elif meth == "addVipValue" and (params.get("value") or params.get("vipExp")):
        per_account = f"每账号 value={params.get('value') or params.get('vipExp')}"
    elif meth == "getVipInfo":
        per_account = "每账号查询 VIP经验值"
    elif meth == "incrNobelLevel" and (params.get("value") or params.get("num")):
        per_account = f"每账号 value={params.get('value') or params.get('num')}"
    elif meth in ("incrUserSendGiftDiamondsNum", "incrUserReceiveGiftDiamondsNum") and params.get(
        "num"
    ):
        per_account = f"每账号 num={params['num']}"
    elif meth == "queryLoginStatusV2":
        per_account = "每账号按手机号查询 userId"
    else:
        shared = [
            f"{key}={val}"
            for key, val in params.items()
            if key not in _BATCH_PARAM_ID_KEYS
        ]
        if shared:
            per_account = "，".join(shared[:6])
        else:
            per_account = "批量参数"
    return f"{per_account}（共 {batch_n} 个账号，不逐一列出）"


_SOURCE_DISPLAY = {"moa": "MOA", "admin": "Admin", "risk": "风控"}


def _tool_result_summary(*, source: str, ok: bool, response: dict[str, Any]) -> tuple[bool, str]:
    if source == "moa":
        return _result_from_response(response)
    if source == "risk":
        ec = response.get("ec")
        success = ec in (0, "0") or str(response.get("msg") or "").lower() == "success"
        if success:
            return True, "成功"
        return False, f"失败（ec={ec}, {response.get('msg') or ''}）".strip()
    if source == "admin":
        ec = response.get("ec")
        status = response.get("status")
        if ec in (0, "0", 200, "200", None) and status not in (1, "1", "fail", "FAIL"):
            if isinstance(status, int) and status not in (0, 200):
                if status != 0:
                    return False, f"失败（status={status}）"
            return True, "成功"
        if status in (0, "0", "success", "SUCCESS"):
            return True, "成功"
        if ec in (0, "0", 200, "200"):
            return True, "成功"
        return False, f"失败（ec={ec}, status={status}）"
    return ok, "成功" if ok else "失败"


def _refresh_tool_operation_field(entry: dict[str, Any]) -> None:
    source = str(entry.get("source") or "moa")
    meth = str(entry.get("method") or "")
    batch_total = int(entry.get("callCount") or 1)
    merged_account = str(entry.get("accountSummary") or "")
    params_text = str(entry.get("paramsSummary") or "")
    if source == "moa":
        entry["operation"] = format_operation_display(
            str(entry.get("operation") or ""),
            method=meth,
            params_summary=params_text,
            account_summary=merged_account,
            call_count=batch_total,
        )
        return
    base = str(entry.get("operation") or "").strip()
    if batch_total > 1 and base and "等" not in base and "批量" not in base:
        first = _primary_user_id(params={}, account_summary=merged_account)
        if first:
            entry["operation"] = f"{first} 等 {batch_total} 项 · {base}"
        else:
            entry["operation"] = f"批量 {batch_total} 项 · {base}"


def record_tool_call(
    *,
    source: str,
    response: dict[str, Any],
    operation: str = "",
    account_summary: str = "",
    service_url: str = "",
    method: str = "",
    params_summary: str = "",
    interface_display: str = "",
    batch_key: str = "",
    run_id: str = "",
    operator_staff_id: str = "",
    operator_name: str = "",
    environment: str = "",
    record_on_failure: bool = False,
) -> None:
    """Web Agent 操作审计：MOA / Admin / 风控等（同 run + 同 operationKey 合并批量）。"""
    src = (source or "moa").strip().lower()
    service_url = str(service_url or "")
    method = str(method or "")
    op_key = f"{src}#{service_url}#{method}"
    run = (run_id or "").strip()
    batch = (batch_key or "").strip()

    staff = (operator_staff_id or "").strip()
    name = (operator_name or "").strip()
    if not staff and not name:
        staff, name = _resolve_operator_from_batch_key(batch)

    operator_display = name or staff or "未知"
    if _operator_name_unknown({"operatorName": operator_display}):
        return

    ok, result_piece = _tool_result_summary(source=src, ok=True, response=response)
    if not ok and not record_on_failure:
        return

    env = (environment or "").strip() or "test"
    iface = (interface_display or "").strip() or format_moa_interface_display(
        service_url=service_url,
        method=method,
    )
    op_text = (operation or "").strip() or iface or src

    entries = _load_entries()
    merge_target: dict[str, Any] | None = None
    if run and op_key:
        for item in reversed(entries):
            if item.get("runId") == run and item.get("operationKey") == op_key:
                merge_target = item
                break

    now = _now_iso_utc()
    if merge_target is not None:
        merge_target["ts"] = now
        merge_target["callCount"] = int(merge_target.get("callCount") or 1) + 1
        if ok:
            merge_target["successCount"] = int(merge_target.get("successCount") or 0) + 1
        else:
            merge_target["failCount"] = int(merge_target.get("failCount") or 0) + 1
        sc = int(merge_target.get("successCount") or 0)
        fc = int(merge_target.get("failCount") or 0)
        total = sc + fc
        if total > 1:
            merge_target["resultSummary"] = f"成功 {sc}/{total}" + (f"，失败 {fc}" if fc else "")
        else:
            merge_target["resultSummary"] = result_piece
        batch_total = int(merge_target.get("callCount") or 1)
        merge_target["accountSummary"] = _merge_account_summary(
            str(merge_target.get("accountSummary") or ""),
            account_summary,
            call_count=batch_total,
        )
        merged_account = str(merge_target.get("accountSummary") or account_summary)
        latest_params = params_summary or str(merge_target.get("paramsSummary") or "")
        merge_target["paramsSummary"] = collapse_batch_params_summary(
            latest_params,
            method=method if src == "moa" else "",
            call_count=batch_total,
            account_summary=merged_account,
        )
        _refresh_tool_operation_field(merge_target)
        prev_count = batch_total - 1
        _save_entries(entries)
        try:
            from web_online_moa_notify import maybe_notify_online_moa_after_record

            maybe_notify_online_moa_after_record(
                merge_target,
                operator_staff_id=staff,
                is_new_entry=False,
                previous_call_count=prev_count,
            )
        except Exception:  # noqa: BLE001
            pass
        return

    entry: dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "ts": now,
        "source": src,
        "operatorStaffId": staff,
        "operatorName": operator_display,
        "operation": op_text,
        "accountSummary": account_summary,
        "serviceUrl": service_url,
        "method": method,
        "moaInterface": iface,
        "paramsSummary": params_summary,
        "resultSummary": result_piece,
        "environment": env,
        "runId": run,
        "batchKey": batch,
        "operationKey": op_key,
        "callCount": 1,
        "successCount": 1 if ok else 0,
        "failCount": 0 if ok else 1,
    }
    _refresh_tool_operation_field(entry)
    entries.append(entry)
    _save_entries(entries)
    try:
        from web_online_moa_notify import maybe_notify_online_moa_after_record

        maybe_notify_online_moa_after_record(
            entry,
            operator_staff_id=staff,
            is_new_entry=True,
        )
    except Exception:  # noqa: BLE001
        pass


def record_moa_call(
    *,
    payload: dict[str, Any],
    response: dict[str, Any],
    payload_file: str = "",
    batch_key: str = "",
    run_id: str = "",
    operator_staff_id: str = "",
    operator_name: str = "",
    environment: str = "",
) -> None:
    """追加或合并一条 MOA 调用记录（同 run + 同 service/method 合并批量）。"""
    service_url = str(payload.get("url") or "")
    method = str(payload.get("method") or "")
    account = _extract_account_hint(payload)
    params_summary = extract_params_summary_from_payload(payload, method=method)
    operation = format_operation_display(
        _operation_label(payload_file=payload_file, service_url=service_url, method=method),
        method=method,
        params_summary=params_summary,
        account_summary=account,
        call_count=1,
    )
    moa_interface = format_moa_interface_display(service_url=service_url, method=method)
    record_tool_call(
        source="moa",
        response=response,
        operation=operation,
        account_summary=account,
        service_url=service_url,
        method=method,
        params_summary=params_summary,
        interface_display=moa_interface,
        batch_key=batch_key,
        run_id=run_id,
        operator_staff_id=operator_staff_id,
        operator_name=operator_name,
        environment=environment,
        record_on_failure=True,
    )


def list_moa_call_entries(*, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 100), 500))
    safe_offset = max(0, int(offset or 0))
    entries = [
        item
        for item in _load_entries()
        if not _operator_name_unknown(item) and str(item.get("source") or "") != "backfill"
    ]
    entries.sort(key=lambda item: str(item.get("ts") or ""), reverse=True)
    total = len(entries)
    slice_rows = entries[safe_offset : safe_offset + safe_limit]
    rows: list[dict[str, Any]] = []
    for raw in slice_rows:
        row = dict(raw)
        row["timeBj"] = iso_to_bj_display(str(raw.get("ts") or ""))
        src = str(raw.get("source") or "moa").strip().lower()
        src_label = _SOURCE_DISPLAY.get(src, src)
        iface = format_moa_interface_display(
            service_url=str(raw.get("serviceUrl") or ""),
            method=str(raw.get("method") or ""),
            moa_interface=str(raw.get("moaInterface") or ""),
        )
        row["source"] = src
        row["sourceDisplay"] = src_label
        row["moaInterfaceDisplay"] = f"{src_label} · {iface}" if iface else src_label
        meth = str(raw.get("method") or "")
        call_total = int(raw.get("callCount") or 1)
        account_raw = str(raw.get("accountSummary") or "")
        row["paramsSummary"] = collapse_batch_params_summary(
            str(raw.get("paramsSummary") or ""),
            method=meth if src == "moa" else "",
            call_count=call_total,
            account_summary=account_raw,
        )
        row["accountSummary"] = format_account_summary_display(
            str(raw.get("accountSummary") or ""),
            environment=str(raw.get("environment") or "test"),
        )
        display_entry = dict(raw)
        display_entry["paramsSummary"] = row["paramsSummary"]
        _refresh_tool_operation_field(display_entry)
        row["operation"] = str(display_entry.get("operation") or raw.get("operation") or "")
        rows.append(row)
    return {
        "entries": rows,
        "total": total,
        "offset": safe_offset,
        "limit": safe_limit,
        "hasMore": safe_offset + len(rows) < total,
    }
