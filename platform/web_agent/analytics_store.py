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


_STORE: AnalyticsStore | None = None


def get_analytics_store() -> AnalyticsStore:
    global _STORE
    if _STORE is None:
        _STORE = AnalyticsStore()
    return _STORE
