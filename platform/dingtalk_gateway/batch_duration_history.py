"""批量操作耗时历史：落盘记录单项耗时，供批量进度 ETA 统计。"""

from __future__ import annotations

import json
import logging
import statistics
import threading
import time
from pathlib import Path

from env_loader import GATEWAY_DIR

logger = logging.getLogger("dingtalk-gateway")

DATA_DIR = GATEWAY_DIR / "data"
HISTORY_PATH = DATA_DIR / "batch_duration_history.json"
MAX_RECORDS_PER_LABEL = 50
DEFAULT_LABEL = "批量"


def normalize_batch_label(label: str) -> str:
    text = (label or "").strip()
    return text or DEFAULT_LABEL


class BatchDurationHistoryStore:
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
            logger.warning("读取 batch_duration_history.json 失败，将重建: %s", exc)
            return {}
        if not isinstance(raw, dict):
            return {}
        records: dict[str, list[dict[str, object]]] = {}
        for label, items in raw.items():
            if not isinstance(label, str) or not isinstance(items, list):
                continue
            cleaned: list[dict[str, object]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                try:
                    total = int(item.get("total") or 0)
                    duration = float(item.get("durationS") or 0)
                    sec_per_item = float(item.get("secPerItem") or 0)
                except (TypeError, ValueError):
                    continue
                if total <= 0 or duration <= 0 or sec_per_item <= 0:
                    continue
                cleaned.append(
                    {
                        "total": total,
                        "durationS": round(duration, 1),
                        "secPerItem": round(sec_per_item, 3),
                        "status": str(item.get("status") or "ok"),
                        "recordedAt": item.get("recordedAt"),
                    }
                )
            if cleaned:
                records[normalize_batch_label(label)] = cleaned[-MAX_RECORDS_PER_LABEL:]
        return records

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record(
        self,
        label: str,
        *,
        total: int,
        duration_s: float,
        status: str = "ok",
    ) -> None:
        key = normalize_batch_label(label)
        total_n = max(1, int(total))
        duration = max(0.0, float(duration_s))
        if duration <= 0:
            return
        sec_per_item = duration / total_n
        entry = {
            "total": total_n,
            "durationS": round(duration, 1),
            "secPerItem": round(sec_per_item, 3),
            "status": status,
            "recordedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with self._lock:
            bucket = self._records.setdefault(key, [])
            bucket.append(entry)
            if len(bucket) > MAX_RECORDS_PER_LABEL:
                del bucket[:-MAX_RECORDS_PER_LABEL]
            self._save()
        logger.info(
            "批量耗时已记录 label=%s total=%s duration=%.1fs sec/item=%.3f status=%s",
            key,
            total_n,
            duration,
            sec_per_item,
            status,
        )

    def estimate_sec_per_item(self, label: str) -> float | None:
        key = normalize_batch_label(label)
        with self._lock:
            durations = self._successful_sec_per_item_locked(key)
        if not durations:
            return None
        return float(statistics.median(durations))

    def estimate_total_seconds(self, label: str, total: int) -> float | None:
        spi = self.estimate_sec_per_item(label)
        if spi is None:
            return None
        return spi * max(1, int(total))

    def _successful_sec_per_item_locked(self, label: str) -> list[float]:
        items = self._records.get(label, [])
        values: list[float] = []
        for item in items:
            if str(item.get("status")) != "ok":
                continue
            try:
                values.append(float(item["secPerItem"]))
            except (KeyError, TypeError, ValueError):
                continue
        return values

    def summary(self, label: str | None = None) -> dict[str, object]:
        with self._lock:
            if label:
                key = normalize_batch_label(label)
                items = self._records.get(key, [])
                durations = self._successful_sec_per_item_locked(key)
                median = float(statistics.median(durations)) if durations else None
                return {
                    "label": key,
                    "count": len(items),
                    "medianSecPerItem": median,
                }
            return {
                "labels": sorted(self._records.keys()),
                "counts": {k: len(v) for k, v in self._records.items()},
            }


_store: BatchDurationHistoryStore | None = None
_store_lock = threading.Lock()


def get_batch_duration_store() -> BatchDurationHistoryStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = BatchDurationHistoryStore()
        return _store
