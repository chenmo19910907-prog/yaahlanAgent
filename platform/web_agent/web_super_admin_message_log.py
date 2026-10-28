"""超管资料卡钉钉私聊发送记录。"""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from web_moa_call_log import iso_to_bj_display
from web_session_store import resolve_web_agent_data_dir

LOG_PATH = resolve_web_agent_data_dir() / "super_admin_message_log.json"
AUDIT_JSONL_PATH = LOG_PATH.parent / "super_admin_message_log_audit.jsonl"
_LOG_THREAD_LOCK = threading.RLock()
_LOG_FLOCK_FD: int | None = None
_BACKFILL_ONCE_DONE = False
logger = logging.getLogger("web-agent")
MAX_ENTRIES = 2000
HISTORICAL_MESSAGE_PLACEHOLDER = "（历史发送，正文未记录）"


def has_recorded_message_body(message: str) -> bool:
    body = (message or "").strip()
    return bool(body) and body != HISTORICAL_MESSAGE_PLACEHOLDER


def _lock_path() -> Path:
    return LOG_PATH.parent / ".super_admin_message_log.lock"


def _ensure_flock_fd() -> int:
    global _LOG_FLOCK_FD
    if _LOG_FLOCK_FD is None:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LOG_FLOCK_FD = os.open(str(_lock_path()), os.O_CREAT | os.O_RDWR)
    return _LOG_FLOCK_FD


def _atomic_write(text: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOG_PATH.with_name(f"{LOG_PATH.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, LOG_PATH)
    finally:
        tmp.unlink(missing_ok=True)


def _read_entries() -> list[dict[str, Any]]:
    if not LOG_PATH.is_file():
        return []
    try:
        data = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


@contextmanager
def _exclusive() -> Iterator[None]:
    with _LOG_THREAD_LOCK:
        fd = _ensure_flock_fd()
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def _edit() -> Iterator[list[dict[str, Any]]]:
    with _exclusive():
        entries = _read_entries()
        yield entries
        trimmed = entries[-MAX_ENTRIES:]
        _atomic_write(json.dumps(trimmed, ensure_ascii=False, indent=2) + "\n")


def _backfill_key(*, target_staff_id: str, sent_at: str) -> str:
    blob = f"{target_staff_id}|{sent_at}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


def _append_audit_jsonl(payload: dict[str, Any]) -> None:
    AUDIT_JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    with open(AUDIT_JSONL_PATH, "a", encoding="utf-8") as fh:
        fh.write(line)
    logger.info("超管资料卡私聊 audit=%s", json.dumps(payload, ensure_ascii=False))


def append_super_admin_message_log(
    *,
    operator_staff_id: str,
    operator_label: str,
    target_staff_id: str,
    target_label: str,
    message: str,
    sent_at: str | None = None,
) -> dict[str, Any]:
    ts = (sent_at or "").strip() or datetime.now(timezone.utc).isoformat()
    target_id = (target_staff_id or "").strip()
    body = (message or "").strip()
    entry: dict[str, Any] = {
        "id": uuid.uuid4().hex[:16],
        "sentAt": ts,
        "operatorStaffId": (operator_staff_id or "").strip(),
        "operatorLabel": (operator_label or "").strip(),
        "targetStaffId": target_id,
        "targetLabel": (target_label or "").strip(),
        "message": body,
        "source": "live",
    }
    audit_payload = {
        "sentAt": ts,
        "operatorStaffId": entry["operatorStaffId"],
        "operatorLabel": entry["operatorLabel"],
        "targetStaffId": target_id,
        "targetLabel": entry["targetLabel"],
        "message": body,
    }
    try:
        _append_audit_jsonl(audit_payload)
    except OSError as exc:
        logger.warning("超管资料卡审计写入失败: %s", exc)
    with _edit() as entries:
        entries.append(entry)
    return entry


def _sent_at_epoch(sent_at: str) -> float | None:
    raw = (sent_at or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _live_entry_covers(existing: dict[str, Any], *, target: str, sent_at: str) -> bool:
    if str(existing.get("source") or "") == "backfill":
        return False
    if str(existing.get("targetStaffId") or "").strip() != target:
        return False
    a = _sent_at_epoch(str(existing.get("sentAt") or ""))
    b = _sent_at_epoch(sent_at)
    if a is None or b is None:
        return False
    return abs(a - b) <= 10.0


def merge_backfill_entries(rows: list[dict[str, Any]]) -> int:
    """幂等合并回溯记录，返回新增条数。"""
    if not rows:
        return 0
    existing_keys: set[str] = set()
    existing_live: list[dict[str, Any]] = []
    with _exclusive():
        for item in _read_entries():
            key = str(item.get("backfillKey") or "").strip()
            if key:
                existing_keys.add(key)
            else:
                target = str(item.get("targetStaffId") or "").strip()
                sent = str(item.get("sentAt") or "").strip()
                if target and sent:
                    existing_keys.add(_backfill_key(target_staff_id=target, sent_at=sent))
            if str(item.get("source") or "") != "backfill":
                existing_live.append(item)

    to_add: list[dict[str, Any]] = []
    for raw in rows:
        target = str(raw.get("targetStaffId") or "").strip()
        sent = str(raw.get("sentAt") or "").strip()
        if not target or not sent:
            continue
        key = str(raw.get("backfillKey") or "").strip() or _backfill_key(
            target_staff_id=target, sent_at=sent
        )
        if key in existing_keys:
            continue
        if any(_live_entry_covers(item, target=target, sent_at=sent) for item in existing_live):
            continue
        raw_message = str(raw.get("message") or "").strip()
        if not has_recorded_message_body(raw_message):
            continue
        operator_staff = str(raw.get("operatorStaffId") or "").strip()
        operator_label = str(raw.get("operatorLabel") or "").strip()
        if not operator_staff and not operator_label:
            operator_label = "（历史）"
        to_add.append(
            {
                "id": uuid.uuid4().hex[:16],
                "sentAt": sent,
                "operatorStaffId": operator_staff,
                "operatorLabel": operator_label,
                "targetStaffId": target,
                "targetLabel": str(raw.get("targetLabel") or "").strip(),
                "message": raw_message,
                "source": "backfill",
                "backfillKey": key,
            }
        )
        existing_keys.add(key)

    if not to_add:
        return 0
    with _edit() as entries:
        entries.extend(to_add)
    return len(to_add)


def _maybe_backfill_once() -> None:
    global _BACKFILL_ONCE_DONE
    if _BACKFILL_ONCE_DONE:
        return
    _BACKFILL_ONCE_DONE = True
    try:
        from web_super_admin_message_log_backfill import ensure_super_admin_message_log_backfill

        ensure_super_admin_message_log_backfill()
    except ImportError:
        pass


def list_super_admin_message_entries(
    *,
    limit: int = 50,
    offset: int = 0,
    target_staff_id: str | None = None,
) -> dict[str, Any]:
    _maybe_backfill_once()
    safe_limit = max(1, min(int(limit or 50), 200))
    safe_offset = max(0, int(offset or 0))
    target_filter = (target_staff_id or "").strip()

    with _exclusive():
        entries = _read_entries()

    if target_filter:
        entries = [
            item
            for item in entries
            if str(item.get("targetStaffId") or "").strip() == target_filter
        ]

    entries = [
        item
        for item in entries
        if has_recorded_message_body(str(item.get("message") or ""))
    ]

    entries.sort(key=lambda item: str(item.get("sentAt") or ""), reverse=True)
    total = len(entries)
    slice_rows = entries[safe_offset : safe_offset + safe_limit]
    rows: list[dict[str, Any]] = []
    for raw in slice_rows:
        row = dict(raw)
        row["timeBj"] = iso_to_bj_display(str(raw.get("sentAt") or ""))
        rows.append(row)
    return {
        "entries": rows,
        "total": total,
        "limit": safe_limit,
        "offset": safe_offset,
        "hasMore": safe_offset + len(rows) < total,
    }
