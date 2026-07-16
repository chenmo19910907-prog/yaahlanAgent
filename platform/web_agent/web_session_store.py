"""Web Agent 会话与消息历史（落盘，重启可恢复）。"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("web-agent")

WEB_AGENT_DIR = Path(__file__).resolve().parent
DATA_DIR = WEB_AGENT_DIR / "data"
SESSIONS_INDEX = DATA_DIR / "sessions.json"
MESSAGES_DIR = DATA_DIR / "messages"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
        minutes = int(delta.total_seconds() // 60)
        if minutes < 1:
            return "刚刚"
        if minutes < 60:
            return f"{minutes} 分钟前"
        hours = minutes // 60
        if hours < 24:
            return f"{hours} 小时前"
        days = hours // 24
        if days < 30:
            return f"{days} 天前"
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return ""


@dataclass
class ChatMessage:
    role: str
    content: str
    timestamp: str = field(default_factory=_now_iso)


@dataclass
class SessionMeta:
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": self.message_count,
            "relative_time": _rel_time(self.updated_at),
        }


class WebSessionStore:
    def __init__(
        self,
        index_path: Path = SESSIONS_INDEX,
        messages_dir: Path = MESSAGES_DIR,
    ) -> None:
        self._index_path = index_path
        self._messages_dir = messages_dir
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionMeta] = self._load_index()

    def _load_index(self) -> dict[str, SessionMeta]:
        if not self._index_path.is_file():
            return {}
        try:
            raw = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取 sessions.json 失败: %s", exc)
            return {}
        if not isinstance(raw, dict):
            return {}
        sessions: dict[str, SessionMeta] = {}
        for sid, item in raw.items():
            if not isinstance(item, dict):
                continue
            sessions[str(sid)] = SessionMeta(
                id=str(sid),
                title=str(item.get("title") or "新对话"),
                created_at=str(item.get("created_at") or _now_iso()),
                updated_at=str(item.get("updated_at") or _now_iso()),
                message_count=int(item.get("message_count") or 0),
            )
        return sessions

    def _save_index(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            sid: {
                "title": meta.title,
                "created_at": meta.created_at,
                "updated_at": meta.updated_at,
                "message_count": meta.message_count,
            }
            for sid, meta in self._sessions.items()
        }
        self._index_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _messages_path(self, session_id: str) -> Path:
        return self._messages_dir / f"{session_id}.json"

    def _load_messages(self, session_id: str) -> list[ChatMessage]:
        path = self._messages_path(session_id)
        if not path.is_file():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        messages: list[ChatMessage] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "")
            if role not in ("user", "assistant") or not content.strip():
                continue
            messages.append(
                ChatMessage(
                    role=role,
                    content=content,
                    timestamp=str(item.get("timestamp") or _now_iso()),
                )
            )
        return messages

    def _save_messages(self, session_id: str, messages: list[ChatMessage]) -> None:
        self._messages_dir.mkdir(parents=True, exist_ok=True)
        payload = [
            {"role": m.role, "content": m.content, "timestamp": m.timestamp}
            for m in messages
        ]
        self._messages_path(session_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_sessions(self) -> list[SessionMeta]:
        with self._lock:
            items = [s for s in self._sessions.values() if s.message_count > 0]
        items.sort(key=lambda s: s.updated_at, reverse=True)
        return items

    def create_session(self, *, title: str = "新对话") -> SessionMeta:
        sid = uuid.uuid4().hex[:16]
        now = _now_iso()
        meta = SessionMeta(id=sid, title=title.strip() or "新对话", created_at=now, updated_at=now)
        with self._lock:
            self._sessions[sid] = meta
            self._save_index()
        self._save_messages(sid, [])
        return meta

    def get_session(self, session_id: str) -> SessionMeta | None:
        with self._lock:
            return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            if session_id not in self._sessions:
                return False
            del self._sessions[session_id]
            self._save_index()
        path = self._messages_path(session_id)
        if path.is_file():
            path.unlink(missing_ok=True)
        return True

    def get_messages(self, session_id: str) -> list[ChatMessage]:
        with self._lock:
            if session_id not in self._sessions:
                return []
        return self._load_messages(session_id)

    def append_message(self, session_id: str, role: str, content: str) -> ChatMessage | None:
        text = (content or "").strip()
        if not text:
            return None
        with self._lock:
            meta = self._sessions.get(session_id)
            if meta is None:
                return None
            messages = self._load_messages(session_id)
            msg = ChatMessage(role=role, content=text)
            messages.append(msg)
            self._save_messages(session_id, messages)
            meta.message_count = len(messages)
            meta.updated_at = _now_iso()
            if role == "user" and (meta.title == "新对话" or len(messages) == 1):
                meta.title = text[:40] + ("…" if len(text) > 40 else "")
            self._save_index()
        return msg

    def user_key(self, session_id: str) -> str:
        return f"web:{session_id}"


_STORE: WebSessionStore | None = None


def get_session_store() -> WebSessionStore:
    global _STORE
    if _STORE is None:
        _STORE = WebSessionStore()
    return _STORE
