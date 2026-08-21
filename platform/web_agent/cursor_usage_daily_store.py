"""按用户、按自然日缓存 Cursor 用量（仅历史自然日；本日不入库，次日按历史加载后再缓存）。"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analytics_store import BJ

logger = logging.getLogger("web-agent")

WEB_AGENT_DIR = Path(__file__).resolve().parent
STORE_PATH = WEB_AGENT_DIR / "data" / "cursor_usage_daily_cache.json"


def _today_key_bj() -> str:
    return datetime.now(BJ).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CursorUsageDailyStore:
    def __init__(self, path: Path = STORE_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self._path.is_file():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取 Cursor 按日用量缓存失败: %s", exc)
            return {}
        users = raw.get("users") if isinstance(raw, dict) else None
        if not isinstance(users, dict):
            return {}
        out: dict[str, dict[str, Any]] = {}
        for staff_id, item in users.items():
            sid = str(staff_id or "").strip()
            if not sid or not isinstance(item, dict):
                continue
            days_raw = item.get("days")
            if not isinstance(days_raw, dict):
                continue
            days: dict[str, dict[str, int]] = {}
            for day_key, stats in days_raw.items():
                dk = str(day_key or "").strip()
                if not dk or not isinstance(stats, dict):
                    continue
                days[dk] = {
                    "requests": int(stats.get("requests") or 0),
                    "tokens": int(stats.get("tokens") or 0),
                }
            if days:
                out[sid] = {"days": days}
        return out

    def _save(self, users: dict[str, dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"users": users}
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_day(self, staff_id: str, day_key: str) -> dict[str, int] | None:
        sid = (staff_id or "").strip()
        dk = (day_key or "").strip()
        if not sid or not dk:
            return None
        with self._lock:
            row = self._load().get(sid, {})
        days = row.get("days") if isinstance(row, dict) else None
        if not isinstance(days, dict):
            return None
        stats = days.get(dk)
        if not isinstance(stats, dict):
            return None
        return {
            "requests": int(stats.get("requests") or 0),
            "tokens": int(stats.get("tokens") or 0),
        }

    def set_days(
        self,
        staff_id: str,
        daily: dict[str, dict[str, int]],
    ) -> None:
        sid = (staff_id or "").strip()
        if not sid or not daily:
            return
        today_key = _today_key_bj()
        with self._lock:
            users = self._load()
            row = users.setdefault(sid, {"days": {}, "updatedAt": _now_iso()})
            days = row.setdefault("days", {})
            if not isinstance(days, dict):
                days = {}
                row["days"] = days
            for day_key, stats in daily.items():
                dk = str(day_key or "").strip()
                if not dk or dk >= today_key or not isinstance(stats, dict):
                    continue
                days[dk] = {
                    "requests": int(stats.get("requests") or 0),
                    "tokens": int(stats.get("tokens") or 0),
                }
            row["updatedAt"] = _now_iso()
            users[sid] = row
            self._save(users)

    def remove_day(self, staff_id: str, day_key: str) -> None:
        sid = (staff_id or "").strip()
        dk = (day_key or "").strip()
        if not sid or not dk:
            return
        with self._lock:
            users = self._load()
            row = users.get(sid)
            if not isinstance(row, dict):
                return
            days = row.get("days")
            if not isinstance(days, dict) or dk not in days:
                return
            days.pop(dk, None)
            row["updatedAt"] = _now_iso()
            users[sid] = row
            self._save(users)

    def purge_today(self, staff_id: str) -> None:
        self.remove_day(staff_id, _today_key_bj())

    def earliest_day_with_data(
        self,
        staff_id: str,
        since_day: str,
        until_day: str,
    ) -> str | None:
        sid = (staff_id or "").strip()
        since = (since_day or "").strip()
        until = (until_day or "").strip()
        if not sid or not since or not until or since > until:
            return None
        with self._lock:
            row = self._load().get(sid, {})
        days = row.get("days") if isinstance(row, dict) else None
        if not isinstance(days, dict):
            return None
        earliest: str | None = None
        for day_key, stats in days.items():
            dk = str(day_key or "").strip()
            if not dk or dk < since or dk > until or not isinstance(stats, dict):
                continue
            if int(stats.get("requests") or 0) <= 0 and int(stats.get("tokens") or 0) <= 0:
                continue
            if earliest is None or dk < earliest:
                earliest = dk
        return earliest

    def trim_leading_empty_days(
        self,
        staff_id: str,
        since_day: str,
        until_day: str,
    ) -> str | None:
        """删除 since..until 内最早非零日之前的缓存；返回最早非零日。"""
        earliest = self.earliest_day_with_data(staff_id, since_day, until_day)
        if not earliest:
            return None
        sid = (staff_id or "").strip()
        with self._lock:
            users = self._load()
            row = users.get(sid)
            if not isinstance(row, dict):
                return earliest
            days = row.get("days")
            if not isinstance(days, dict):
                return earliest
            removed = False
            for day_key in list(days.keys()):
                dk = str(day_key or "").strip()
                if dk and dk < earliest:
                    days.pop(day_key, None)
                    removed = True
            if removed:
                row["updatedAt"] = _now_iso()
                users[sid] = row
                self._save(users)
        return earliest

    def clear_staff(self, staff_id: str) -> None:
        sid = (staff_id or "").strip()
        if not sid:
            return
        with self._lock:
            users = self._load()
            if sid in users:
                users.pop(sid, None)
                self._save(users)


_STORE: CursorUsageDailyStore | None = None


def get_cursor_usage_daily_store() -> CursorUsageDailyStore:
    global _STORE
    if _STORE is None:
        _STORE = CursorUsageDailyStore()
    return _STORE
