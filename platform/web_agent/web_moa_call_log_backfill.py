"""从 Web Agent 历史会话/Run 回溯 MOA 调用记录（每轮对话合并一条）。"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from web_moa_call_log import (
    LOG_PATH,
    _load_entries,
    _save_entries,
    extract_moa_call_details_from_assistant,
    iso_to_bj_display,
)

WEB_AGENT_DIR = Path(__file__).resolve().parent
RUNS_DIR = WEB_AGENT_DIR / "data" / "runs"
MESSAGES_DIR = WEB_AGENT_DIR / "data" / "messages"
BACKFILL_MARKER = WEB_AGENT_DIR / "data" / "moa_call_log_backfill.json"

_USER_ID_RE = re.compile(r"\b1\d{5,8}\b")
_BATCH_RESULT_RE = re.compile(
    r"成功\s*/\s*失败[^0-9]*(\d+)\s*/\s*(\d+)",
    re.I,
)
_MOA_TABLE_OP_ROW_RE = re.compile(
    r"操作\s*[|｜]\s*([^|\n]+?)\s*(?:[|｜]|$)",
    re.I,
)
_MOA_OP_PAREN_METHOD_RE = re.compile(
    r"^(.+?)[（(]\s*`?([^`）)\n]+)`?\s*[）)]\s*$",
)
_POOR_OPERATION_RE = re.compile(
    r"^(?:ec\s*[=:]\s*\d+|ec=\d+|msg\s*:|em\s*:|success\b|\d{5,11}$|，模板在)",
    re.I,
)
_SKIP_USER_RE = re.compile(
    r"MOA检查|检查MOA|MOA探活|MOA入库|接入了多少\s*MOA|MOA地址|能做一个MOA调用记录|"
    r"历史记录|工具平台|打开Web|怎么用|有哪些能力",
    re.I,
)
_SKIP_ASSISTANT_RE = re.compile(
    r"任务已中断|暂无.*MOA|没有.*MOA|无法识别|MOA 调用分两层|已接入\s*\*\*\d+",
    re.I,
)
_MOA_EXEC_ASSISTANT_RE = re.compile(
    r"moa_execute|成功/失败|"
    r"MOA\s+`[^`]+`\s*/\s*`[^`]+`|"
    r"`/service/[^`]+`\s*·|"
    r"provideDiamond|setUserNotBanSpeak|likeContent|"
    r"已为.{0,32}(?:发放|解除|升级|下发|加白|创建|设为)|"
    r"\"ec\":\s*0|ec=200|ec=0[^0-9]|"
    r"操作成功|验收通过",
    re.I,
)


def _entry_key(session_id: str, user_ts: str, user_text: str) -> str:
    blob = f"{session_id}|{user_ts}|{user_text[:200]}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _existing_backfill_keys(entries: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for item in entries:
        key = str(item.get("backfillKey") or "").strip()
        if key:
            keys.add(key)
        run_id = str(item.get("runId") or "").strip()
        if run_id.startswith("backfill:"):
            keys.add(run_id[9:])
    return keys


def _is_poor_operation_label(label: str) -> bool:
    s = (label or "").strip()
    if not s or len(s) < 2:
        return True
    if _POOR_OPERATION_RE.match(s):
        return True
    if re.fullmatch(r"ec\s*:\s*\d+.*", s, re.I):
        return True
    return False


def _user_operation_fallback(user_text: str) -> str:
    line = " ".join((user_text or "").split())
    return line[:80] if line else "MOA 操作"


def _label_from_table_operation_cell(cell: str) -> str:
    raw = (cell or "").strip()
    if not raw or _is_poor_operation_label(raw):
        return ""
    pm = _MOA_OP_PAREN_METHOD_RE.match(raw)
    if pm:
        title = (pm.group(1) or "").strip()
        method = (pm.group(2) or "").strip()
        if title and method and not _is_poor_operation_label(method):
            return f"{title}（{method}）"[:80]
        if title:
            return title[:80]
    return raw[:80]


def _summarize_operation(user_text: str, assistant_text: str) -> str:
    assistant = assistant_text or ""

    m = _MOA_TABLE_OP_ROW_RE.search(assistant)
    if m:
        label = _label_from_table_operation_cell(m.group(1) or "")
        if label:
            return label

    for tpl in re.findall(r"MOA/templates/([^`\s]+\.json)", assistant, re.I):
        return Path(tpl).stem

    for svc_m in re.finditer(r"`(/service/[^`\s]+)`\s*·\s*`([^`]+)`", assistant):
        meth = (svc_m.group(2) or "").strip()
        if meth and not _is_poor_operation_label(meth):
            return meth[:80]
        svc = svc_m.group(1)
        return svc.split("/")[-1]

    for svc in re.findall(r"`(/service/[^`\s]+)`", assistant):
        return svc.split("/")[-1]

    for pat in re.finditer(r"(?:^|\n)[^\n]*\bMOA\b[^`\n]*`([^`]+)`", assistant, re.I):
        cand = (pat.group(1) or "").strip()
        if _is_poor_operation_label(cand):
            continue
        if cand.endswith(".json"):
            return Path(cand).stem
        return cand[:80]

    return _user_operation_fallback(user_text)


def _summarize_account(user_text: str, assistant_text: str) -> str:
    blob = f"{user_text}\n{assistant_text}"
    ids = _USER_ID_RE.findall(blob)
    if not ids:
        phones = re.findall(r"1[3-9]\d{9}", blob)
        if phones:
            return phones[0]
        return ""
    uniq: list[str] = []
    seen: set[str] = set()
    for uid in ids:
        if uid not in seen:
            seen.add(uid)
            uniq.append(uid)
    if len(uniq) == 1:
        return uniq[0]
    if len(uniq) <= 3:
        return "、".join(uniq)
    return f"{uniq[0]} 等 {len(uniq)} 个账号"


def _summarize_result(assistant_text: str) -> tuple[str, int, int, int]:
    m = _BATCH_RESULT_RE.search(assistant_text)
    if m:
        ok, fail = int(m.group(1)), int(m.group(2))
        total = ok + fail
        return f"成功 {ok}/{total}" + (f"，失败 {fail}" if fail else ""), total, ok, fail
    if _SKIP_ASSISTANT_RE.search(assistant_text):
        return "未完成", 1, 0, 1
    if re.search(r"失败|错误|ec=\d{3,}", assistant_text, re.I) and not re.search(
        r"ec=200|ec=0[^0-9]|成功", assistant_text, re.I
    ):
        return "失败（历史回溯）", 1, 0, 1
    return "成功（历史回溯）", 1, 1, 0


def _pair_qualifies(user_text: str, assistant_text: str) -> bool:
    user = (user_text or "").strip()
    assistant = (assistant_text or "").strip()
    if not user or not assistant or len(assistant) < 40:
        return False
    if _SKIP_USER_RE.search(user) or _SKIP_ASSISTANT_RE.search(assistant):
        return False
    if not _MOA_EXEC_ASSISTANT_RE.search(assistant):
        return False
    if re.search(r"已实现|已修复|已录入|刷新.*即可", assistant) and not _MOA_EXEC_ASSISTANT_RE.search(
        assistant
    ):
        return False
    return True


def _append_backfill_entry(
    entries: list[dict[str, Any]],
    *,
    backfill_key: str,
    ts_iso: str,
    operator_staff_id: str,
    operator_name: str,
    operation: str,
    account_summary: str,
    result_summary: str,
    call_count: int,
    success_count: int,
    fail_count: int,
    session_id: str,
    run_id: str = "",
    moa_details: dict[str, str] | None = None,
) -> bool:
    if backfill_key in _existing_backfill_keys(entries):
        return False
    details = moa_details or {}
    entries.append(
        {
            "id": hashlib.sha256(backfill_key.encode()).hexdigest()[:24],
            "ts": ts_iso,
            "operatorStaffId": operator_staff_id,
            "operatorName": operator_name or operator_staff_id or "未知",
            "operation": operation,
            "accountSummary": account_summary,
            "serviceUrl": details.get("serviceUrl") or "",
            "method": details.get("method") or "",
            "moaInterface": details.get("moaInterface") or "",
            "paramsSummary": details.get("paramsSummary") or "",
            "resultSummary": result_summary,
            "environment": "test",
            "runId": run_id or f"backfill:{backfill_key}",
            "batchKey": f"web:{session_id}" if session_id else "",
            "operationKey": f"backfill#{backfill_key[:16]}",
            "callCount": call_count,
            "successCount": success_count,
            "failCount": fail_count,
            "source": "backfill",
            "backfillKey": backfill_key,
        }
    )
    return True


def _iter_message_pairs(path: Path) -> list[dict[str, Any]]:
    session_id = path.stem
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(rows, list):
        return []
    pairs: list[dict[str, Any]] = []
    pending_user: dict[str, Any] | None = None
    for item in rows:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        if role == "user":
            pending_user = item
            continue
        if role != "assistant" or pending_user is None:
            continue
        pairs.append(
            {
                "session_id": session_id,
                "user_text": str(pending_user.get("content") or ""),
                "user_ts": str(pending_user.get("timestamp") or ""),
                "author_id": str(pending_user.get("author_id") or ""),
                "author_label": str(pending_user.get("author_label") or ""),
                "assistant_text": str(item.get("content") or ""),
                "assistant_ts": str(item.get("timestamp") or ""),
            }
        )
        pending_user = None
    return pairs


def _index_backfill_pairs() -> dict[str, dict[str, Any]]:
    """backfillKey -> message pair（用于修正历史 operation 文案）。"""
    index: dict[str, dict[str, Any]] = {}
    if not MESSAGES_DIR.is_dir():
        return index
    for path in sorted(MESSAGES_DIR.glob("*.json")):
        if path.suffix != ".json" or path.name.endswith((".tail", ".search")):
            continue
        for pair in _iter_message_pairs(path):
            key = _entry_key(pair["session_id"], pair["user_ts"], pair["user_text"])
            index[key] = pair
    return index


def repair_backfill_call_details() -> dict[str, Any]:
    """为回溯记录补全/刷新 serviceUrl、method、paramsSummary。"""
    entries = _load_entries()
    pairs = _index_backfill_pairs()
    fixed = 0
    for item in entries:
        bf_key = str(item.get("backfillKey") or "").strip()
        if not bf_key:
            run_id = str(item.get("runId") or "")
            if run_id.startswith("backfill:"):
                bf_key = run_id[9:]
        if not bf_key:
            continue
        pair = pairs.get(bf_key)
        if not pair:
            continue
        details = extract_moa_call_details_from_assistant(pair["assistant_text"])
        changed = False
        for field in ("serviceUrl", "method", "moaInterface", "paramsSummary"):
            new_val = (details.get(field) or "").strip()
            old_val = str(item.get(field) or "").strip()
            if field == "paramsSummary":
                if new_val and new_val != old_val:
                    item[field] = new_val
                    changed = True
                continue
            if not new_val:
                continue
            if new_val != old_val:
                item[field] = new_val
                changed = True
        if changed:
            fixed += 1
    if fixed:
        _save_entries(entries)
    return {"fixed": fixed, "total": len(entries)}


def repair_backfill_operation_labels() -> dict[str, Any]:
    """按会话原文重算回溯记录的 operation（修正 ec: 0 等误识别）。"""
    entries = _load_entries()
    pairs = _index_backfill_pairs()
    fixed = 0
    for item in entries:
        bf_key = str(item.get("backfillKey") or "").strip()
        if not bf_key:
            run_id = str(item.get("runId") or "")
            if run_id.startswith("backfill:"):
                bf_key = run_id[9:]
        if not bf_key:
            continue
        old_op = str(item.get("operation") or "")
        pair = pairs.get(bf_key)
        if not pair:
            continue
        new_op = _summarize_operation(pair["user_text"], pair["assistant_text"])
        if new_op == old_op or _is_poor_operation_label(new_op):
            continue
        if not _is_poor_operation_label(old_op) and new_op == _user_operation_fallback(pair["user_text"]):
            continue
        item["operation"] = new_op
        fixed += 1
    if fixed:
        _save_entries(entries)
    return {"fixed": fixed, "total": len(entries)}


def backfill_moa_call_log(*, force: bool = False) -> dict[str, Any]:
    """扫描历史会话并写入 moa_call_log.json（幂等）。"""
    if BACKFILL_MARKER.is_file() and not force:
        try:
            marker = json.loads(BACKFILL_MARKER.read_text(encoding="utf-8"))
            if isinstance(marker, dict) and marker.get("completed"):
                return {"skipped": True, "reason": "already_completed", **marker}
        except (OSError, json.JSONDecodeError):
            pass

    entries = _load_entries()
    before = len(entries)
    added = 0
    scanned_pairs = 0

    if MESSAGES_DIR.is_dir():
        for path in sorted(MESSAGES_DIR.glob("*.json")):
            if path.suffix != ".json" or path.name.endswith((".tail", ".search")):
                continue
            for pair in _iter_message_pairs(path):
                scanned_pairs += 1
                if not _pair_qualifies(pair["user_text"], pair["assistant_text"]):
                    continue
                key = _entry_key(pair["session_id"], pair["user_ts"], pair["user_text"])
                ts = (pair["assistant_ts"] or pair["user_ts"] or "").strip()
                if not ts:
                    ts = datetime.now(timezone.utc).isoformat()
                op = _summarize_operation(pair["user_text"], pair["assistant_text"])
                acct = _summarize_account(pair["user_text"], pair["assistant_text"])
                result, total, ok, fail = _summarize_result(pair["assistant_text"])
                moa_details = extract_moa_call_details_from_assistant(pair["assistant_text"])
                if _append_backfill_entry(
                    entries,
                    backfill_key=key,
                    ts_iso=ts,
                    operator_staff_id=pair["author_id"],
                    operator_name=pair["author_label"],
                    operation=op,
                    account_summary=acct,
                    result_summary=result,
                    call_count=max(total, 1),
                    success_count=ok,
                    fail_count=fail,
                    session_id=pair["session_id"],
                    moa_details=moa_details,
                ):
                    added += 1

    entries.sort(key=lambda x: str(x.get("ts") or ""))
    _save_entries(entries[-2000:])
    after = len(_load_entries())
    summary = {
        "completed": True,
        "scanned_pairs": scanned_pairs,
        "added": added,
        "total_before": before,
        "total_after": after,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    BACKFILL_MARKER.parent.mkdir(parents=True, exist_ok=True)
    BACKFILL_MARKER.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MOA 历史调用记录回溯 / 修正")
    parser.add_argument("--repair-operations", action="store_true", help="修正 operation 误识别（如 ec: 0）")
    parser.add_argument(
        "--repair-call-details",
        action="store_true",
        help="补全/刷新接口与参数（历史回溯）",
    )
    parser.add_argument("--force-backfill", action="store_true", help="重新扫描会话并追加回溯记录")
    args = parser.parse_args()
    if args.repair_call_details:
        print(json.dumps(repair_backfill_call_details(), ensure_ascii=False, indent=2))
    elif args.repair_operations:
        print(json.dumps(repair_backfill_operation_labels(), ensure_ascii=False, indent=2))
    elif args.force_backfill:
        print(json.dumps(backfill_moa_call_log(force=True), ensure_ascii=False, indent=2))
    else:
        parser.print_help()
