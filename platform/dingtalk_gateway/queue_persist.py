"""排队任务持久化（崩溃恢复时仅记录，无法自动重放钉钉消息）。"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from env_loader import GATEWAY_DIR

logger = logging.getLogger("dingtalk-gateway")

DATA_DIR = GATEWAY_DIR / "data"
PENDING_PATH = DATA_DIR / "pending_queue.json"


@dataclass
class PendingRecord:
    user_key: str
    prompt: str
    lane: str
    conversation_id: str | None
    sender_staff_id: str | None
    enqueued_at: str


class QueuePersist:
    def __init__(self, path: Path = PENDING_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._items: list[PendingRecord] = self._load()

    def _load(self) -> list[PendingRecord]:
        if not self._path.is_file():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取 pending_queue.json 失败: %s", exc)
            return []
        items = raw.get("items") if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return []
        records: list[PendingRecord] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            prompt = str(item.get("prompt") or "").strip()
            if not prompt:
                continue
            records.append(
                PendingRecord(
                    user_key=str(item.get("user_key") or ""),
                    prompt=prompt,
                    lane=str(item.get("lane") or "agent"),
                    conversation_id=item.get("conversation_id"),
                    sender_staff_id=item.get("sender_staff_id"),
                    enqueued_at=str(item.get("enqueued_at") or ""),
                )
            )
        return records

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"items": [asdict(item) for item in self._items]}
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add(
        self,
        *,
        user_key: str,
        prompt: str,
        lane: str,
        conversation_id: str | None,
        sender_staff_id: str | None,
    ) -> None:
        record = PendingRecord(
            user_key=user_key,
            prompt=prompt,
            lane=lane,
            conversation_id=conversation_id,
            sender_staff_id=sender_staff_id,
            enqueued_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
        with self._lock:
            self._items.append(record)
            self._save()

    def remove(self, *, user_key: str, prompt: str) -> None:
        with self._lock:
            self._items = [
                item
                for item in self._items
                if not (item.user_key == user_key and item.prompt == prompt)
            ]
            self._save()

    def drain_stale_on_startup(self) -> list[PendingRecord]:
        with self._lock:
            stale = list(self._items)
            self._items.clear()
            self._save()
        return stale


_persist: QueuePersist | None = None
_persist_lock = threading.Lock()


def get_queue_persist() -> QueuePersist:
    global _persist
    with _persist_lock:
        if _persist is None:
            _persist = QueuePersist()
        return _persist
