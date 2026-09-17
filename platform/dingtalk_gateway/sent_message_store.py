"""机器人 outbound 消息 processQueryKey 落盘，供 24h 内撤回。"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from env_loader import GATEWAY_DIR

logger = logging.getLogger("dingtalk-gateway")

DATA_DIR = GATEWAY_DIR / "data"
STORE_PATH = DATA_DIR / "sent_message_keys.json"
RECALL_TTL_S = 24 * 3600
MAX_KEYS_PER_USER = 40
BURST_WINDOW_S = 120.0


@dataclass
class SentMessageRecord:
    process_query_key: str
    sent_at: float
    kind: str = "message"
    label: str = ""


class SentMessageStore:
    def __init__(self, path: Path = STORE_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, list[SentMessageRecord]] = self._load()

    def _load(self) -> dict[str, list[SentMessageRecord]]:
        if not self._path.is_file():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取 sent_message_keys.json 失败: %s", exc)
            return {}
        if not isinstance(raw, dict):
            return {}
        out: dict[str, list[SentMessageRecord]] = {}
        for user_key, items in raw.items():
            if not isinstance(items, list):
                continue
            records: list[SentMessageRecord] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("process_query_key") or "").strip()
                if not key:
                    continue
                records.append(
                    SentMessageRecord(
                        process_query_key=key,
                        sent_at=float(item.get("sent_at") or 0.0),
                        kind=str(item.get("kind") or "message"),
                        label=str(item.get("label") or ""),
                    )
                )
            if records:
                out[str(user_key)] = records
        return out

    def _persist_locked(self) -> None:
        payload = {
            user_key: [
                {
                    "process_query_key": rec.process_query_key,
                    "sent_at": rec.sent_at,
                    "kind": rec.kind,
                    "label": rec.label,
                }
                for rec in records
            ]
            for user_key, records in self._data.items()
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _prune_locked(self, records: list[SentMessageRecord]) -> list[SentMessageRecord]:
        now = time.time()
        kept = [rec for rec in records if now - rec.sent_at <= RECALL_TTL_S]
        if len(kept) > MAX_KEYS_PER_USER:
            kept = kept[-MAX_KEYS_PER_USER:]
        return kept

    def register(
        self,
        user_key: str,
        process_query_key: str,
        *,
        kind: str = "message",
        label: str = "",
    ) -> None:
        key = (process_query_key or "").strip()
        uk = (user_key or "").strip()
        if not key or not uk:
            return
        with self._lock:
            records = self._prune_locked(self._data.get(uk, []))
            records.append(
                SentMessageRecord(
                    process_query_key=key,
                    sent_at=time.time(),
                    kind=kind,
                    label=label,
                )
            )
            self._data[uk] = records
            self._persist_locked()

    def pop_recent_keys(self, user_key: str, *, count: int = 1) -> list[str]:
        uk = (user_key or "").strip()
        if not uk or count <= 0:
            return []
        with self._lock:
            records = self._prune_locked(self._data.get(uk, []))
            if not records:
                self._data[uk] = []
                self._persist_locked()
                return []
            take = min(count, len(records))
            picked = records[-take:]
            self._data[uk] = records[:-take]
            self._persist_locked()
            return [rec.process_query_key for rec in picked]

    def pop_burst_keys(self, user_key: str, *, window_s: float = BURST_WINDOW_S) -> list[str]:
        """撤回同一轮回复（如流式卡 + 结果消息，默认 120s 内连发）。"""
        uk = (user_key or "").strip()
        if not uk:
            return []
        now = time.time()
        with self._lock:
            records = self._prune_locked(self._data.get(uk, []))
            if not records:
                self._data[uk] = []
                self._persist_locked()
                return []
            picked: list[SentMessageRecord] = []
            for rec in reversed(records):
                if now - rec.sent_at > window_s:
                    break
                picked.append(rec)
            if not picked:
                picked = [records[-1]]
            remain = records[: len(records) - len(picked)]
            self._data[uk] = remain
            self._persist_locked()
            return [rec.process_query_key for rec in reversed(picked)]

    def recent_count(self, user_key: str) -> int:
        uk = (user_key or "").strip()
        if not uk:
            return 0
        with self._lock:
            return len(self._prune_locked(self._data.get(uk, [])))

    def remove_key(self, user_key: str, process_query_key: str) -> bool:
        uk = (user_key or "").strip()
        key = (process_query_key or "").strip()
        if not uk or not key:
            return False
        with self._lock:
            records = self._prune_locked(self._data.get(uk, []))
            remain = [rec for rec in records if rec.process_query_key != key]
            if len(remain) == len(records):
                return False
            self._data[uk] = remain
            self._persist_locked()
            return True


_STORE: SentMessageStore | None = None
_STORE_LOCK = threading.Lock()


def get_sent_message_store() -> SentMessageStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = SentMessageStore()
        return _STORE
