"""Web Agent 用户行为打点：JSONL 落盘与汇总。"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("web-agent")

WEB_AGENT_DIR = Path(__file__).resolve().parent
EVENTS_PATH = WEB_AGENT_DIR / "data" / "analytics" / "events.jsonl"
MESSAGES_DIR = WEB_AGENT_DIR / "data" / "messages"

BJ = timezone(timedelta(hours=8))

USAGE_RANGE_LABELS: dict[str, str] = {
    "day": "本日",
    "week": "本周",
    "month": "本月",
    "7d": "7天内",
    "30d": "30天内",
}
DEFAULT_USAGE_RANGE = "month"

_EVENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_\-]{0,63}$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_event_name(name: str) -> str:
    raw = (name or "").strip().lower().replace(" ", "_")
    raw = re.sub(r"[^a-z0-9_\-]", "", raw)
    if not raw or not _EVENT_NAME_RE.match(raw):
        return ""
    return raw


def _parse_ts(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def estimate_tokens_from_text(text: str) -> int:
    raw = str(text or "")
    if not raw.strip():
        return 0
    return max(1, (len(raw) + 2) // 3)


def resolve_usage_range(range_key: str) -> tuple[datetime, datetime, str, str]:
    """返回 (start_utc, end_utc, label, normalized_key)，边界按北京时间。"""
    now_bj = datetime.now(BJ)
    end = now_bj.astimezone(timezone.utc)
    key = (range_key or DEFAULT_USAGE_RANGE).strip().lower()
    if key not in USAGE_RANGE_LABELS:
        key = DEFAULT_USAGE_RANGE

    if key == "day":
        start_bj = now_bj.replace(hour=0, minute=0, second=0, microsecond=0)
    elif key == "week":
        start_bj = (now_bj - timedelta(days=now_bj.weekday())).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    elif key == "month":
        start_bj = now_bj.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif key == "7d":
        # 含今天共 7 个自然日（非 8 个）
        start_bj = (now_bj - timedelta(days=6)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    else:  # 30d
        start_bj = (now_bj - timedelta(days=29)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    start = start_bj.astimezone(timezone.utc)
    return start, end, USAGE_RANGE_LABELS[key], key


def _sanitize_props(props: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(props, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in props.items():
        name = str(key or "").strip()[:64]
        if not name:
            continue
        if isinstance(value, bool):
            out[name] = value
        elif isinstance(value, (int, float)):
            out[name] = value
        elif value is None:
            continue
        else:
            text = str(value).strip()
            if text:
                out[name] = text[:256]
    return out


class AnalyticsStore:
    def __init__(self, events_path: Path = EVENTS_PATH) -> None:
        self._events_path = events_path
        self._lock = threading.Lock()

    def record_event(
        self,
        *,
        event: str,
        page: str = "",
        staff_id: str = "",
        display_name: str = "",
        source: str = "server",
        props: dict[str, Any] | None = None,
        ip: str = "",
    ) -> bool:
        normalized = normalize_event_name(event)
        if not normalized:
            return False
        payload = {
            "ts": _now_iso(),
            "event": normalized,
            "page": (page or "").strip()[:256],
            "staff_id": (staff_id or "").strip()[:64],
            "display_name": (display_name or "").strip()[:64],
            "source": (source or "server").strip()[:16],
            "ip": (ip or "").strip()[:64],
            "props": _sanitize_props(props),
        }
        self._events_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False)
        try:
            with self._lock:
                with open(self._events_path, "a", encoding="utf-8") as fp:
                    fp.write(line + "\n")
        except OSError as exc:
            logger.warning("写入 analytics 失败: %s", exc)
            return False
        return True

    def iter_events(self) -> list[dict[str, Any]]:
        if not self._events_path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        try:
            for line in self._events_path.read_text(encoding="utf-8").splitlines():
                text = line.strip()
                if not text:
                    continue
                try:
                    item = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
        except OSError as exc:
            logger.warning("读取 analytics 失败: %s", exc)
        return rows

    def summarize(self, *, days: int = 30, limit: int = 100) -> dict[str, Any]:
        window_days = max(1, min(int(days or 30), 365))
        max_items = max(1, min(int(limit or 100), 500))
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

        total = 0
        by_event: dict[str, int] = defaultdict(int)
        by_page: dict[str, int] = defaultdict(int)
        page_uv: dict[str, set[str]] = defaultdict(set)
        event_uv: dict[str, set[str]] = defaultdict(set)
        daily: dict[str, int] = defaultdict(int)

        for row in self.iter_events():
            ts = _parse_ts(str(row.get("ts") or ""))
            if ts is None or ts < cutoff:
                continue
            total += 1
            event = str(row.get("event") or "").strip() or "unknown"
            page = str(row.get("page") or "").strip() or "(unknown)"
            staff_id = str(row.get("staff_id") or "").strip()
            by_event[event] += 1
            if event == "page_view":
                by_page[page] += 1
                if staff_id:
                    page_uv[page].add(staff_id)
            if staff_id:
                event_uv[event].add(staff_id)
            day_key = ts.astimezone(timezone.utc).strftime("%Y-%m-%d")
            daily[day_key] += 1

        def _top_counter(counter: dict[str, int]) -> list[dict[str, Any]]:
            items = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
            return [
                {"key": key, "count": count}
                for key, count in items[:max_items]
            ]

        return {
            "days": window_days,
            "total": total,
            "by_event": _top_counter(by_event),
            "by_page": _top_counter(by_page),
            "page_uv": [
                {"page": page, "uv": len(users), "pv": by_page.get(page, 0)}
                for page, users in sorted(
                    page_uv.items(),
                    key=lambda item: (-by_page.get(item[0], 0), item[0]),
                )[:max_items]
            ],
            "event_uv": [
                {"event": event, "uv": len(users), "count": by_event.get(event, 0)}
                for event, users in sorted(
                    event_uv.items(),
                    key=lambda item: (-by_event.get(item[0], 0), item[0]),
                )[:max_items]
            ],
            "daily": [
                {"date": day, "count": daily[day]}
                for day in sorted(daily.keys())
            ],
        }

    def _estimate_tokens_from_messages(
        self,
        staff_id: str,
        *,
        start: datetime,
        end: datetime,
    ) -> int:
        sid = (staff_id or "").strip()
        if not sid or not MESSAGES_DIR.is_dir():
            return 0
        total = 0
        overhead_per_request = 800
        for path in MESSAGES_DIR.glob("*.json"):
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(rows, list):
                continue
            for index, row in enumerate(rows):
                if not isinstance(row, dict) or row.get("role") != "user":
                    continue
                if str(row.get("author_id") or "").strip() != sid:
                    continue
                ts = _parse_ts(str(row.get("timestamp") or ""))
                if ts is None or ts < start or ts > end:
                    continue
                total += overhead_per_request
                total += estimate_tokens_from_text(str(row.get("content") or ""))
                for follow in rows[index + 1 :]:
                    if not isinstance(follow, dict):
                        continue
                    if follow.get("role") == "user":
                        break
                    if follow.get("role") == "assistant":
                        total += estimate_tokens_from_text(str(follow.get("content") or ""))
                        break
        return total

    def summarize_user_usage(
        self,
        staff_id: str,
        *,
        range_key: str = DEFAULT_USAGE_RANGE,
    ) -> dict[str, Any]:
        sid = (staff_id or "").strip()
        start, end, label, key = resolve_usage_range(range_key)
        if not sid:
            return {
                "range": key,
                "rangeLabel": label,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "requests": 0,
                "tokens": 0,
                "tokensSource": "none",
            }

        requests = 0
        tokens_recorded = 0
        completes = 0
        for row in self.iter_events():
            ts = _parse_ts(str(row.get("ts") or ""))
            if ts is None or ts < start or ts > end:
                continue
            if str(row.get("staff_id") or "").strip() != sid:
                continue
            event = str(row.get("event") or "").strip()
            if event == "chat_send":
                requests += 1
                continue
            if event != "chat_complete":
                continue
            completes += 1
            props = row.get("props")
            if not isinstance(props, dict):
                continue
            raw_tokens = props.get("total_tokens")
            if isinstance(raw_tokens, (int, float)) and raw_tokens > 0:
                tokens_recorded += int(raw_tokens)

        tokens = tokens_recorded
        tokens_source = "recorded" if completes >= requests and tokens_recorded > 0 else "none"
        if tokens_source != "recorded" and requests > 0:
            tokens = self._estimate_tokens_from_messages(sid, start=start, end=end)
            tokens_source = "estimated" if tokens > 0 else "none"

        return {
            "range": key,
            "rangeLabel": label,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "requests": requests,
            "tokens": tokens,
            "tokensSource": tokens_source,
        }


_STORE: AnalyticsStore | None = None


def get_analytics_store() -> AnalyticsStore:
    global _STORE
    if _STORE is None:
        _STORE = AnalyticsStore()
    return _STORE
