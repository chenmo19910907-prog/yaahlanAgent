"""按群会话记住上一条任务，供「重新执行」。"""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class ConversationRecord:
    prompt: str
    summary: str = ""
    last_full_reply: str = ""


class ConversationStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, ConversationRecord] = {}

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
