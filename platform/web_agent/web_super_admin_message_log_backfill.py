"""从 server.log / 审计 jsonl 回溯超管资料卡私聊发送记录。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from calendar import month_abbr
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from web_session_store import resolve_web_agent_data_dir

logger = logging.getLogger("web-agent")

WEB_AGENT_DIR = Path(__file__).resolve().parent
DATA_DIR = resolve_web_agent_data_dir()
SERVER_LOG = DATA_DIR / "server.log"
AUDIT_JSONL = DATA_DIR / "super_admin_message_log_audit.jsonl"
BACKFILL_MARKER = DATA_DIR / "super_admin_message_log_backfill.json"

_BJ = timezone(timedelta(hours=8))

_ACCESS_SEND_RE = re.compile(
    r'\[(\d{1,2}/(\w{3})/\d{4} \d{2}:\d{2}:\d{2})\] "POST /api/admin/user-profile/send-message'
)
_PRIV_SEND_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ INFO 私聊文本已发送 staff=(\d+)…"
)
_AUDIT_LOG_RE = re.compile(r"超管资料卡私聊 audit=(\{.+)$")

_MONTH_MAP = {m: i for i, m in enumerate(month_abbr) if m}


def _backfill_key(*, target_staff_id: str, sent_at: str) -> str:
    blob = f"{target_staff_id}|{sent_at}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


def _parse_access_ts(raw: str) -> datetime | None:
    try:
        day_s, mon_s, rest = raw.split("/", 2)
        mon = _MONTH_MAP.get(mon_s[:3].title())
        if not mon:
            return None
        day = int(day_s)
        year_s, time_s = rest.split(" ", 1)
        year = int(year_s)
        hour, minute, second = (int(x) for x in time_s.split(":"))
        return datetime(year, mon, day, hour, minute, second, tzinfo=_BJ)
    except (ValueError, IndexError):
        return None


def _to_iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_BJ)
    return dt.astimezone(timezone.utc).isoformat()


def _collect_known_staff_ids() -> list[str]:
    ids: set[str] = set()

    def _walk(obj: object) -> None:
        if isinstance(obj, dict):
            for key, val in obj.items():
                if key in ("staffId", "staff_id", "web_owner_id", "operatorStaffId", "targetStaffId"):
                    s = str(val or "").strip()
                    if s.isdigit() and len(s) >= 10:
                        ids.add(s)
                _walk(val)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    for name in ("web_auth_sessions.json", "admin_grants.json", "sessions.json"):
        path = DATA_DIR / name
        if not path.is_file():
            continue
        try:
            _walk(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(ids, key=len, reverse=True)


def _resolve_staff_id(prefix: str, known: list[str]) -> str:
    p = (prefix or "").strip()
    if not p:
        return ""
    for full in known:
        if full.startswith(p):
            return full
    return p


def _load_private_send_index(lines: list[str]) -> list[tuple[datetime, str]]:
    rows: list[tuple[datetime, str]] = []
    for line in lines:
        m = _PRIV_SEND_RE.search(line)
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=_BJ)
        except ValueError:
            continue
        rows.append((ts, m.group(2)))
    return rows


def _match_private_send(
    at: datetime,
    priv_index: list[tuple[datetime, str]],
    *,
    window_s: float = 5.0,
) -> str:
    best_prefix = ""
    best_delta = window_s + 1.0
    for pts, prefix in priv_index:
        delta = abs((pts - at).total_seconds())
        if delta <= window_s and delta < best_delta:
            best_delta = delta
            best_prefix = prefix
    return best_prefix


def _parse_audit_records(lines: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in lines:
        m = _AUDIT_LOG_RE.search(line)
        if not m:
            continue
        try:
            payload = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _parse_server_log_send_events(lines: list[str], known_staff: list[str]) -> list[dict[str, Any]]:
    """server.log 无消息正文，不参与回溯。"""
    del lines, known_staff
    return []


def _normalize_audit_record(raw: dict[str, Any], known_staff: list[str]) -> dict[str, Any] | None:
    target = _resolve_staff_id(str(raw.get("targetStaffId") or ""), known_staff)
    sent_at = str(raw.get("sentAt") or "").strip()
    message = str(raw.get("message") or "").strip()
    if not target or not sent_at or not message:
        return None
    return {
        "sentAt": sent_at,
        "targetStaffId": target,
        "operatorStaffId": str(raw.get("operatorStaffId") or "").strip(),
        "operatorLabel": str(raw.get("operatorLabel") or "").strip(),
        "targetLabel": str(raw.get("targetLabel") or "").strip(),
        "message": message,
        "source": "backfill",
        "backfillKey": _backfill_key(target_staff_id=target, sent_at=sent_at),
    }


def _read_audit_jsonl(known_staff: list[str]) -> list[dict[str, Any]]:
    if not AUDIT_JSONL.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        text = AUDIT_JSONL.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        norm = _normalize_audit_record(raw, known_staff)
        if norm:
            rows.append(norm)
    return rows


def scan_backfill_candidates(*, server_log: Path | None = None) -> list[dict[str, Any]]:
    """扫描可回溯的发送记录（审计 jsonl 优先，其次 server.log）。"""
    known_staff = _collect_known_staff_ids()
    by_key: dict[str, dict[str, Any]] = {}

    for row in _read_audit_jsonl(known_staff):
        key = str(row.get("backfillKey") or "")
        if key:
            by_key[key] = row

    log_path = server_log or SERVER_LOG
    if log_path.is_file():
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
        for row in _parse_audit_records(lines):
            norm = _normalize_audit_record(row, known_staff)
            if not norm:
                continue
            key = str(norm.get("backfillKey") or "")
            if key:
                by_key[key] = norm
        for row in _parse_server_log_send_events(lines, known_staff):
            key = str(row.get("backfillKey") or "")
            if key and key not in by_key:
                by_key[key] = row

    return sorted(by_key.values(), key=lambda item: str(item.get("sentAt") or ""))


def backfill_super_admin_message_log(*, force: bool = False) -> dict[str, Any]:
    from web_super_admin_message_log import merge_backfill_entries

    if BACKFILL_MARKER.is_file() and not force:
        try:
            marker = json.loads(BACKFILL_MARKER.read_text(encoding="utf-8"))
            if isinstance(marker, dict) and marker.get("completed"):
                return {"skipped": True, "reason": "already_completed", **marker}
        except (OSError, json.JSONDecodeError):
            pass

    candidates = scan_backfill_candidates()
    added = merge_backfill_entries(candidates)
    summary = {
        "completed": True,
        "scanned": len(candidates),
        "added": added,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    BACKFILL_MARKER.parent.mkdir(parents=True, exist_ok=True)
    BACKFILL_MARKER.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if added:
        logger.info("超管资料卡发送记录回溯：新增 %s 条", added)
    return summary


def ensure_super_admin_message_log_backfill() -> None:
    try:
        backfill_super_admin_message_log(force=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("超管资料卡发送记录回溯失败: %s", exc)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="超管资料卡私聊发送记录回溯")
    parser.add_argument("--force", action="store_true", help="忽略已完成标记并重新扫描")
    args = parser.parse_args()
    print(json.dumps(backfill_super_admin_message_log(force=args.force), ensure_ascii=False, indent=2))
