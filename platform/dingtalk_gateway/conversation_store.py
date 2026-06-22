"""按群会话记住上一条任务，供「重新执行」。"""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class ConversationRecord:
    prompt: str
    summary: str = ""


class ConversationStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, ConversationRecord] = {}

    @staticmethod
    def conversation_key(conversation_id: str | None, sender_id: str | None = None) -> str:
        if conversation_id:
            return conversation_id
        if sender_id:
            return f"dm:{sender_id}"
        return "default"

    def save(self, conversation_id: str | None, prompt: str, *, sender_id: str | None = None) -> None:
        text = (prompt or "").strip()
        if not text:
            return
        key = self.conversation_key(conversation_id, sender_id)
        with self._lock:
            self._records[key] = ConversationRecord(prompt=text, summary=text[:80])

    def get_last(self, conversation_id: str | None, *, sender_id: str | None = None) -> str | None:
        key = self.conversation_key(conversation_id, sender_id)
        with self._lock:
            record = self._records.get(key)
        return record.prompt if record else None

    def get_summary(self, conversation_id: str | None, *, sender_id: str | None = None) -> str | None:
        key = self.conversation_key(conversation_id, sender_id)
        with self._lock:
            record = self._records.get(key)
        return record.summary if record else None
