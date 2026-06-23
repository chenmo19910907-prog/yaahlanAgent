"""按群会话记住上一条任务，供「重新执行」；落盘 survives 重启。"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from env_loader import GATEWAY_DIR

logger = logging.getLogger("dingtalk-gateway")

DATA_DIR = GATEWAY_DIR / "data"
CONVERSATIONS_INDEX = DATA_DIR / "conversations.json"


@dataclass
class ConversationRecord:
    prompt: str
    summary: str = ""
    last_full_reply: str = ""


class ConversationStore:
    def __init__(self, index_path: Path = CONVERSATIONS_INDEX) -> None:
        self._index_path = index_path
        self._lock = threading.Lock()
        self._records: dict[str, ConversationRecord] = self._load()

    @staticmethod
    def conversation_key(
        conversation_id: str | None,
        sender_id: str | None = None,
        *,
        sender_staff_id: str | None = None,
        conversation_type: str | None = None,
    ) -> str:
        user = (sender_staff_id or sender_id or "").strip()
        if conversation_type == "1" or not conversation_id:
            return f"dm:{user or 'unknown'}"
        if user:
            return f"{conversation_id}:user:{user}"
        return conversation_id or "default"

    def _load(self) -> dict[str, ConversationRecord]:
        if not self._index_path.is_file():
            return {}
        try:
            raw = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取 conversations.json 失败，将重建: %s", exc)
            return {}
        if not isinstance(raw, dict):
            return {}
        records: dict[str, ConversationRecord] = {}
        for key, item in raw.items():
            if not isinstance(item, dict):
                continue
            prompt = str(item.get("prompt") or "").strip()
            if not prompt and not str(item.get("last_full_reply") or "").strip():
                continue
            records[str(key)] = ConversationRecord(
                prompt=prompt,
                summary=str(item.get("summary") or prompt[:80]),
                last_full_reply=str(item.get("last_full_reply") or ""),
            )
        return records

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            key: {
                "prompt": record.prompt,
                "summary": record.summary,
                "last_full_reply": record.last_full_reply,
            }
            for key, record in self._records.items()
        }
        self._index_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save(
        self,
        conversation_id: str | None,
        prompt: str,
        *,
        sender_id: str | None = None,
        sender_staff_id: str | None = None,
        conversation_type: str | None = None,
    ) -> None:
        text = (prompt or "").strip()
        if not text:
            return
        key = self.conversation_key(
            conversation_id,
            sender_id,
            sender_staff_id=sender_staff_id,
            conversation_type=conversation_type,
        )
        with self._lock:
            prev = self._records.get(key)
            self._records[key] = ConversationRecord(
                prompt=text,
                summary=text[:80],
                last_full_reply=prev.last_full_reply if prev else "",
            )
            self._save()

    def save_full_reply(
        self,
        conversation_id: str | None,
        reply: str,
        *,
        sender_id: str | None = None,
        sender_staff_id: str | None = None,
        conversation_type: str | None = None,
    ) -> None:
        body = (reply or "").strip()
        if not body:
            return
        key = self.conversation_key(
            conversation_id,
            sender_id,
            sender_staff_id=sender_staff_id,
            conversation_type=conversation_type,
        )
        with self._lock:
            record = self._records.get(key)
            if record is None:
                self._records[key] = ConversationRecord(
                    prompt="",
                    summary="",
                    last_full_reply=body,
                )
            else:
                record.last_full_reply = body
            self._save()

    def get_last_full_reply(
        self,
        conversation_id: str | None,
        *,
        sender_id: str | None = None,
        sender_staff_id: str | None = None,
        conversation_type: str | None = None,
    ) -> str | None:
        key = self.conversation_key(
            conversation_id,
            sender_id,
            sender_staff_id=sender_staff_id,
            conversation_type=conversation_type,
        )
        with self._lock:
            record = self._records.get(key)
        if record is None or not record.last_full_reply.strip():
            return None
        return record.last_full_reply

    def get_last(
        self,
        conversation_id: str | None,
        *,
        sender_id: str | None = None,
        sender_staff_id: str | None = None,
        conversation_type: str | None = None,
    ) -> str | None:
        key = self.conversation_key(
            conversation_id,
            sender_id,
            sender_staff_id=sender_staff_id,
            conversation_type=conversation_type,
        )
        with self._lock:
            record = self._records.get(key)
        return record.prompt if record else None

    def get_summary(
        self,
        conversation_id: str | None,
        *,
        sender_id: str | None = None,
        sender_staff_id: str | None = None,
        conversation_type: str | None = None,
    ) -> str | None:
        key = self.conversation_key(
            conversation_id,
            sender_id,
            sender_staff_id=sender_staff_id,
            conversation_type=conversation_type,
        )
        with self._lock:
            record = self._records.get(key)
        return record.summary if record else None
