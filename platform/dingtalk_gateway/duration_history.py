"""任务耗时历史：落盘记录并在排队/结果中提供预计参考。"""

from __future__ import annotations

import json
import logging
import re
import statistics
import threading
import time
from pathlib import Path

from env_loader import GATEWAY_DIR
from export_delivery import is_view_all_follow_up
from route_patterns import (
    CATALOG_OPEN_RE,
    ENV_CHECK_RE,
    EXPORT_FILE_RE,
    HELP_RE,
    MOA_CHECK_RE,
    REPORT_NL_RE,
    REPORT_URL_RE,
    REPORT_VERSION_RE,
    VIP_UPGRADE_RE,
    is_likely_fast_route,
)

logger = logging.getLogger("dingtalk-gateway")

DATA_DIR = GATEWAY_DIR / "data"
HISTORY_PATH = DATA_DIR / "duration_history.json"
MAX_RECORDS_PER_KIND = 50
DEFAULT_AGENT_KIND = "agent:general"


def classify_task_kind(
    prompt: str,
    *,
    route_kind: str | None = None,
) -> str:
    """将任务归类，便于统计同类耗时。"""
    if route_kind:
        return f"fast:{route_kind}"
    text = (prompt or "").strip()
    if not text:
        return DEFAULT_AGENT_KIND
    if is_view_all_follow_up(text):
        return "fast:view_all"
    if HELP_RE.match(text):
        return "fast:help"
    if MOA_CHECK_RE.match(text):
        return "fast:moa_check"
    if ENV_CHECK_RE.match(text):
        return "fast:env_check"
    if CATALOG_OPEN_RE.match(text):
        return "fast:catalog"
    if EXPORT_FILE_RE.match(text):
        return "fast:export_file"
    if VIP_UPGRADE_RE.match(text):
        return "fast:vip_upgrade"
    if REPORT_VERSION_RE.match(text) or REPORT_NL_RE.match(text) or REPORT_URL_RE.match(text):
        return "fast:report"
    if re.search(r"测试用例|生成用例|写用例", text):
        return "agent:testcase"
    if re.search(r"送礼|gift", text, re.I):
        return "agent:gift"
    if re.search(r"抓包|tunnel", text, re.I):
        return "agent:tunnel"
    if re.search(r"查询|查\s*user|用户\s*\d{5,}|\d{6,}", text, re.I):
        return "agent:query"
    if re.search(r"修改|代码|网关", text):
        return "agent:code_modify"
    if is_likely_fast_route(text):
        return "fast:other"
    return DEFAULT_AGENT_KIND


class DurationHistoryStore:
    def __init__(self, path: Path = HISTORY_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._records: dict[str, list[dict[str, object]]] = self._load()

    def _load(self) -> dict[str, list[dict[str, object]]]:
        if not self._path.is_file():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取 duration_history.json 失败，将重建: %s", exc)
            return {}
        if not isinstance(raw, dict):
            return {}
        records: dict[str, list[dict[str, object]]] = {}
        for kind, items in raw.items():
            if not isinstance(kind, str) or not isinstance(items, list):
                continue
            cleaned: list[dict[str, object]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                try:
                    duration = float(item.get("durationS", 0))
                except (TypeError, ValueError):
                    continue
                if duration <= 0:
                    continue
                cleaned.append(
                    {
                        "durationS": round(duration, 1),
                        "status": str(item.get("status") or "ok"),
                        "recordedAt": item.get("recordedAt"),
                    }
                )
            if cleaned:
                records[kind] = cleaned[-MAX_RECORDS_PER_KIND:]
        return records

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record(self, task_kind: str, duration_s: float, *, status: str) -> None:
        kind = (task_kind or DEFAULT_AGENT_KIND).strip() or DEFAULT_AGENT_KIND
        duration = max(0.0, float(duration_s))
        if duration <= 0:
            return
        entry = {
            "durationS": round(duration, 1),
            "status": status,
            "recordedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with self._lock:
            bucket = self._records.setdefault(kind, [])
            bucket.append(entry)
            if len(bucket) > MAX_RECORDS_PER_KIND:
                del bucket[:-MAX_RECORDS_PER_KIND]
            self._save()

    def estimate_seconds(self, task_kind: str | None) -> float | None:
        kind = (task_kind or DEFAULT_AGENT_KIND).strip() or DEFAULT_AGENT_KIND
        with self._lock:
            durations = self._successful_durations_locked(kind)
            if not durations and kind.startswith("fast:"):
                durations = self._successful_durations_locked("fast:other")
            if not durations and kind.startswith("agent:"):
                durations = self._successful_durations_locked(DEFAULT_AGENT_KIND)
        if not durations:
            return None
        return float(statistics.median(durations))

    def estimate_agent_seconds(self) -> float | None:
        with self._lock:
            durations: list[float] = []
            for kind, items in self._records.items():
                if not kind.startswith("agent:"):
                    continue
                for item in items:
                    if str(item.get("status")) != "ok":
                        continue
                    try:
                        durations.append(float(item["durationS"]))
                    except (KeyError, TypeError, ValueError):
                        continue
        if not durations:
            return None
        return float(statistics.median(durations))

    def _successful_durations_locked(self, kind: str) -> list[float]:
        items = self._records.get(kind, [])
        durations: list[float] = []
        for item in items:
            if str(item.get("status")) != "ok":
                continue
            try:
                durations.append(float(item["durationS"]))
            except (KeyError, TypeError, ValueError):
                continue
        return durations


_store: DurationHistoryStore | None = None
_store_lock = threading.Lock()


def get_duration_store() -> DurationHistoryStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = DurationHistoryStore()
        return _store
