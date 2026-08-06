"""Web Agent 会话与消息历史（落盘，重启可恢复）。"""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from typing import Any


def sort_sessions_for_display(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """置顶优先；未置顶中思考中优先于其余，组内按 updated_at 降序。"""
    pinned = [s for s in sessions if s.get("pinned")]
    unpinned = [s for s in sessions if not s.get("pinned")]
    pinned.sort(key=lambda s: str(s.get("pinned_at") or ""))
    running = [s for s in unpinned if s.get("running")]
    idle = [s for s in unpinned if not s.get("running")]
    by_updated = lambda s: str(s.get("updated_at") or "")
    running.sort(key=by_updated, reverse=True)
    idle.sort(key=by_updated, reverse=True)
    return pinned + running + idle


logger = logging.getLogger("web-agent")

WEB_AGENT_DIR = Path(__file__).resolve().parent
DATA_DIR = WEB_AGENT_DIR / "data"
SESSIONS_INDEX = DATA_DIR / "sessions.json"
MESSAGES_DIR = DATA_DIR / "messages"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def dingtalk_session_id(dingtalk_key: str) -> str:
    digest = hashlib.sha256(dingtalk_key.encode("utf-8")).hexdigest()[:16]
    return f"dt{digest}"


def parse_dingtalk_user_id(dingtalk_key: str) -> str:
    """从 conversation_key 解析钉钉用户标识（staff_id / sender_id）。"""
    key = (dingtalk_key or "").strip()
    if not key:
        return ""
    if key.startswith("dm:"):
        return key[3:].strip()
    marker = ":user:"
    if marker in key:
        return key.rsplit(marker, 1)[-1].strip()
    return ""


def _title_from_text(text: str) -> str:
    body = (text or "").strip()
    if not body:
        return "新对话"
    return body[:40] + ("…" if len(body) > 40 else "")


def _normalize_custom_title(text: str) -> str:
    body = (text or "").strip()
    if not body:
        return ""
    if len(body) > 80:
        return body[:80]
    return body


def _latest_user_prompt(messages: list[ChatMessage]) -> str:
    for msg in reversed(messages):
        if msg.role == "user":
            content = (msg.content or "").strip()
            if content:
                return content
    return ""


def _turn_already_synced(
    messages: list[ChatMessage], prompt: str, reply: str = ""
) -> bool:
    text = (prompt or "").strip()
    body = (reply or "").strip()
    if not text or not messages:
        return False
    if messages[-1].role != "assistant":
        return False
    for msg in reversed(messages[:-1]):
        if msg.role == "user":
            if msg.content != text:
                return False
            if body:
                return messages[-1].content.strip() == body
            return True
    return False


def _latest_message_timestamp(messages: list[ChatMessage]) -> str:
    best = ""
    best_dt: datetime | None = None
    for msg in messages:
        ts = (msg.timestamp or "").strip()
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        if best_dt is None or dt > best_dt:
            best_dt = dt
            best = ts
    return best or _now_iso()


def _preview_from_messages(messages: list[ChatMessage]) -> str:
    if not messages:
        return ""
    text = (messages[-1].content or "").strip().replace("\n", " ")
    if len(text) > 56:
        return text[:56] + "…"
    return text


def _normalize_search_query(query: str) -> str:
    return " ".join((query or "").strip().split()).casefold()


def _snippet_around(text: str, query: str, *, max_len: int = 80) -> str:
    plain = " ".join((text or "").split())
    if not plain:
        return ""
    q = _normalize_search_query(query)
    if not q:
        return plain[:max_len] + ("…" if len(plain) > max_len else "")
    lower = plain.casefold()
    idx = lower.find(q)
    if idx < 0:
        return plain[:max_len] + ("…" if len(plain) > max_len else "")
    start = max(0, idx - 24)
    end = min(len(plain), idx + len(q) + 36)
    chunk = plain[start:end].strip()
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(plain) else ""
    return f"{prefix}{chunk}{suffix}"


def _session_people_blob(
    meta: SessionMeta,
    known_labels: dict[str, str] | None,
) -> str:
    labels = known_labels or {}
    parts: list[str] = []
    if meta.source == "dingtalk":
        parts.extend([meta.dingtalk_label, meta.dingtalk_owner_id])
        owner_id = (meta.dingtalk_owner_id or "").strip()
        if owner_id:
            parts.append(labels.get(owner_id, ""))
    else:
        parts.extend([meta.web_owner_label, meta.web_owner_id])
        owner_id = (meta.web_owner_id or "").strip()
        if owner_id:
            parts.append(labels.get(owner_id, ""))
        for uid in meta.web_collaborator_ids:
            collab_id = (uid or "").strip()
            if not collab_id:
                continue
            parts.append(collab_id)
            parts.append(labels.get(collab_id, ""))
    return " ".join(part.strip() for part in parts if part and part.strip())


def session_matches_search(
    meta: SessionMeta,
    messages: list[ChatMessage],
    query: str,
    *,
    known_labels: dict[str, str] | None = None,
) -> str:
    """命中则返回展示用摘要，否则返回空字符串。"""
    q = _normalize_search_query(query)
    if not q:
        return ""
    for field in (meta.title, meta.custom_title, meta.latest_preview):
        text = (field or "").strip()
        if text and q in text.casefold():
            return _snippet_around(text, q)
    people = _session_people_blob(meta, known_labels)
    if people and q in people.casefold():
        return _snippet_around(people, q)
    for msg in reversed(messages):
        content = (msg.content or "").strip().replace("\n", " ")
        author = (msg.author_label or msg.author_id or "").strip()
        blob_parts = [content]
        if author:
            blob_parts.append(author)
        blob = " ".join(part for part in blob_parts if part)
        if not blob or q not in blob.casefold():
            continue
        role_tag = "问" if msg.role == "user" else "答"
        return f"{role_tag} · {_snippet_around(blob, q)}"
    return ""


def filter_sessions_by_search(
    sessions: list[SessionMeta],
    query: str,
    *,
    load_messages: Callable[[str], list[ChatMessage]],
    known_labels: dict[str, str] | None = None,
) -> list[tuple[SessionMeta, str]]:
    q = _normalize_search_query(query)
    if not q:
        return [(meta, "") for meta in sessions]
    matched: list[tuple[SessionMeta, str]] = []
    for meta in sessions:
        snippet = session_matches_search(
            meta,
            load_messages(meta.id),
            q,
            known_labels=known_labels,
        )
        if snippet:
            matched.append((meta, snippet))
    return matched


def _session_owner_staff_id(meta: SessionMeta) -> str:
    if meta.source == "dingtalk":
        owner = (meta.dingtalk_owner_id or "").strip()
        if owner:
            return owner
        return parse_dingtalk_user_id(meta.dingtalk_key)
    return (meta.web_owner_id or "").strip()


def filter_sessions_by_scope(
    sessions: list[SessionMeta],
    scope: str,
    *,
    viewer_staff_id: str | None = None,
) -> list[SessionMeta]:
    normalized = (scope or "all").strip().lower()
    if normalized != "mine":
        return sessions
    viewer = (viewer_staff_id or "").strip()
    if not viewer:
        return []
    return [meta for meta in sessions if _session_owner_staff_id(meta) == viewer]


def _auto_titles_from_messages(messages: list[ChatMessage]) -> set[str]:
    titles: set[str] = set()
    for msg in messages:
        if msg.role != "user":
            continue
        text = (msg.content or "").strip()
        if text:
            titles.add(_title_from_text(text))
    return titles


def _maybe_revert_mistaken_custom_title(
    meta: SessionMeta, messages: list[ChatMessage]
) -> bool:
    """误将历史自动标题写入 custom_title 时，在新提问刷新后恢复为自动标题。"""
    custom = (meta.custom_title or "").strip()
    if not custom:
        return False
    latest_user = _latest_user_prompt(messages)
    latest_auto = _title_from_text(latest_user) if latest_user else "新对话"
    if (meta.title or "").strip() != latest_auto:
        return False
    if custom == latest_auto:
        return False
    if custom not in _auto_titles_from_messages(messages):
        return False
    meta.custom_title = ""
    return True


def _maybe_promote_legacy_custom_title(
    meta: SessionMeta, messages: list[ChatMessage]
) -> bool:
    """旧版把手动标题写在 title 字段时，迁移到 custom_title。"""
    if (meta.custom_title or "").strip():
        return False
    stored = (meta.title or "").strip()
    if not stored or stored == "新对话":
        return False
    if stored in _auto_titles_from_messages(messages):
        return False
    latest_user = _latest_user_prompt(messages)
    auto = _title_from_text(latest_user) if latest_user else "新对话"
    if stored == auto:
        return False
    meta.custom_title = _normalize_custom_title(stored)
    meta.title = auto
    return True


def _apply_message_derived_meta(
    meta: SessionMeta,
    messages: list[ChatMessage],
    *,
    custom_title_touched: set[str] | None = None,
) -> bool:
    """用消息内容刷新标题（最新提问）、排序时间与条数。"""
    if not messages:
        meta.latest_preview = ""
        return False
    changed = False
    if _maybe_revert_mistaken_custom_title(meta, messages):
        changed = True
        if custom_title_touched is not None and meta.id:
            custom_title_touched.add(meta.id)
    if _maybe_promote_legacy_custom_title(meta, messages):
        changed = True
    latest_user = _latest_user_prompt(messages)
    if latest_user:
        new_title = _title_from_text(latest_user)
        if meta.title != new_title:
            meta.title = new_title
            changed = True
    new_updated = _latest_message_timestamp(messages)
    if meta.updated_at != new_updated:
        meta.updated_at = new_updated
        changed = True
    count = len(messages)
    if meta.message_count != count:
        meta.message_count = count
        changed = True
    meta.latest_preview = _preview_from_messages(messages)
    return changed


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
    images: list[str] = field(default_factory=list)
    files: list[dict[str, object]] = field(default_factory=list)
    author_id: str = ""
    author_label: str = ""


@dataclass
class SessionMeta:
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0
    source: str = "web"
    dingtalk_key: str = ""
    dingtalk_label: str = ""
    dingtalk_owner_id: str = ""
    web_owner_id: str = ""
    web_owner_label: str = ""
    web_collaborator_ids: list[str] = field(default_factory=list)
    pinned_at: str = ""
    custom_title: str = ""
    latest_preview: str = field(default="", repr=False)

    def display_title(self) -> str:
        custom = (self.custom_title or "").strip()
        if custom:
            return custom
        auto = (self.title or "").strip()
        return auto or "新对话"

    @property
    def is_pinned(self) -> bool:
        return bool((self.pinned_at or "").strip())

    def web_collaborator_id_set(self) -> set[str]:
        return {
            uid.strip()
            for uid in self.web_collaborator_ids
            if isinstance(uid, str) and uid.strip()
        }

    def is_collaborator(self, staff_id: str | None) -> bool:
        viewer = (staff_id or "").strip()
        if not viewer:
            return False
        return viewer in self.web_collaborator_id_set()

    def web_owner_display(self, *, known_labels: dict[str, str] | None = None) -> str:
        from dingtalk_user_lookup import resolve_staff_display_name

        uid = (self.web_owner_id or "").strip()
        label = resolve_staff_display_name(
            uid,
            known_labels=known_labels,
            fallback_label=(self.web_owner_label or "").strip(),
        )
        if label:
            return label
        if uid:
            return f"用户 {uid}"
        return ""

    def owner_display(self, *, known_labels: dict[str, str] | None = None) -> str:
        from dingtalk_user_lookup import resolve_staff_display_name

        owner_id = (self.dingtalk_owner_id or "").strip() or parse_dingtalk_user_id(
            self.dingtalk_key
        )
        label = resolve_staff_display_name(
            owner_id,
            known_labels=known_labels,
            fallback_label=(self.dingtalk_label or "").strip(),
        )
        if label:
            return label
        if owner_id:
            return f"用户 {owner_id}"
        return "未知用户"

    def is_read_only_for_viewer(self, viewer_staff_id: str | None = None) -> bool:
        if self.source == "dingtalk":
            return True
        owner_id = (self.web_owner_id or "").strip()
        if not owner_id:
            return False
        viewer = (viewer_staff_id or "").strip()
        if not viewer:
            return True
        if viewer == owner_id:
            return False
        return not self.is_collaborator(viewer)

    def to_dict(
        self,
        *,
        known_labels: dict[str, str] | None = None,
        viewer_staff_id: str | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "title": self.display_title(),
            "auto_title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": self.message_count,
            "relative_time": _rel_time(self.updated_at),
            "source": self.source,
        }
        if self.source == "dingtalk":
            payload["read_only"] = True
            owner = self.owner_display(known_labels=known_labels)
            payload["dingtalk_owner"] = owner
            if owner:
                payload["dingtalk_label"] = owner
            elif self.dingtalk_label:
                from dingtalk_user_lookup import chinese_display_name

                payload["dingtalk_label"] = chinese_display_name(self.dingtalk_label)
            if self.dingtalk_owner_id:
                payload["dingtalk_owner_id"] = self.dingtalk_owner_id
        elif self.source == "web":
            owner = self.web_owner_display(known_labels=known_labels)
            if owner:
                payload["web_owner"] = owner
                payload["web_owner_label"] = owner
            elif self.web_owner_label:
                from dingtalk_user_lookup import chinese_display_name

                payload["web_owner_label"] = chinese_display_name(self.web_owner_label)
            if self.web_owner_id:
                payload["web_owner_id"] = self.web_owner_id
            collab_ids = sorted(self.web_collaborator_id_set())
            if collab_ids:
                payload["web_collaborator_ids"] = collab_ids
                from dingtalk_user_lookup import _public_display_name, resolve_staff_display_name

                payload["web_collaborators"] = [
                    {
                        "staffId": uid,
                        "displayName": _public_display_name(
                            resolve_staff_display_name(uid, known_labels=known_labels),
                            uid,
                        ),
                    }
                    for uid in collab_ids
                ]
            viewer = (viewer_staff_id or "").strip()
            owner_id = (self.web_owner_id or "").strip()
            if viewer and owner_id and viewer == owner_id:
                payload["is_mine"] = True
                payload["can_manage_collaborators"] = True
            elif viewer and self.is_collaborator(viewer):
                payload["is_collaborator"] = True
            if self.is_read_only_for_viewer(viewer_staff_id):
                payload["read_only"] = True
        preview = (self.latest_preview or "").strip()
        if preview:
            payload["latest_preview"] = preview
        custom = (self.custom_title or "").strip()
        if custom:
            payload["custom_title"] = custom
        payload["pinned"] = self.is_pinned
        if self.is_pinned:
            payload["pinned_at"] = self.pinned_at
        return payload


class WebSessionStore:
    def __init__(
        self,
        index_path: Path = SESSIONS_INDEX,
        messages_dir: Path = MESSAGES_DIR,
    ) -> None:
        self._index_path = index_path
        self._messages_dir = messages_dir
        self._lock = threading.Lock()
        self._index_lock_path = index_path.parent / ".sessions.lock"
        self._index_mtime: float = 0.0
        self._sessions: dict[str, SessionMeta] = {}
        self._custom_title_touched: set[str] = set()
        self._pinned_touched: set[str] = set()
        self._reload_index_if_stale(force=True)

    @contextmanager
    def _exclusive_index(self) -> Iterator[None]:
        """跨进程（Web 服务 / run_worker / 钉钉网关）读写 sessions.json 时串行化。"""
        with self._lock:
            self._index_lock_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(self._index_lock_path), os.O_CREAT | os.O_RDWR)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                self._reload_index_if_stale(force=True)
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def _index_mtime_on_disk(self) -> float:
        try:
            return self._index_path.stat().st_mtime
        except OSError:
            return 0.0

    def _reload_index_if_stale(self, *, force: bool = False) -> None:
        mtime = self._index_mtime_on_disk()
        if not force and mtime <= self._index_mtime:
            return
        self._sessions = self._load_index()
        self._index_mtime = mtime

    def reload_from_disk(self) -> None:
        """多进程（Web 服务 / 钉钉网关）共享落盘时，读前刷新索引。"""
        with self._lock:
            self._reload_index_if_stale(force=True)

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
            raw_collabs = item.get("web_collaborator_ids")
            sessions[str(sid)] = SessionMeta(
                id=str(sid),
                title=str(item.get("title") or "新对话"),
                created_at=str(item.get("created_at") or _now_iso()),
                updated_at=str(item.get("updated_at") or _now_iso()),
                message_count=int(item.get("message_count") or 0),
                source=str(item.get("source") or "web"),
                dingtalk_key=str(item.get("dingtalk_key") or ""),
                dingtalk_label=str(item.get("dingtalk_label") or ""),
                dingtalk_owner_id=str(item.get("dingtalk_owner_id") or ""),
                web_owner_id=str(item.get("web_owner_id") or ""),
                web_owner_label=str(item.get("web_owner_label") or ""),
                web_collaborator_ids=[
                    str(uid).strip()
                    for uid in raw_collabs
                    if str(uid).strip()
                ] if isinstance(raw_collabs, list) else [],
                pinned_at=str(item.get("pinned_at") or "").strip(),
                custom_title=str(item.get("custom_title") or "").strip(),
            )
        return sessions

    def _merge_independent_fields_from_disk(self) -> None:
        """落盘前合并另一进程已写入的独立字段，避免旧内存覆盖 custom_title / 置顶等。"""
        disk_sessions = self._load_index()
        if not disk_sessions:
            return
        for sid, meta in self._sessions.items():
            disk_meta = disk_sessions.get(sid)
            if disk_meta is None:
                continue
            disk_custom = (disk_meta.custom_title or "").strip()
            if (
                disk_custom
                and not (meta.custom_title or "").strip()
                and sid not in self._custom_title_touched
            ):
                meta.custom_title = disk_meta.custom_title
            if (
                (disk_meta.pinned_at or "").strip()
                and not (meta.pinned_at or "").strip()
                and sid not in self._pinned_touched
            ):
                meta.pinned_at = disk_meta.pinned_at
            if disk_meta.web_collaborator_ids and not meta.web_collaborator_ids:
                meta.web_collaborator_ids = list(disk_meta.web_collaborator_ids)
        for sid, disk_meta in disk_sessions.items():
            if sid not in self._sessions:
                self._sessions[sid] = disk_meta

    def _save_index(self) -> None:
        self._merge_independent_fields_from_disk()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            sid: {
                "title": meta.title,
                "created_at": meta.created_at,
                "updated_at": meta.updated_at,
                "message_count": meta.message_count,
                "source": meta.source,
                "dingtalk_key": meta.dingtalk_key,
                "dingtalk_label": meta.dingtalk_label,
                "dingtalk_owner_id": meta.dingtalk_owner_id,
                "web_owner_id": meta.web_owner_id,
                "web_owner_label": meta.web_owner_label,
                **(
                    {"web_collaborator_ids": sorted(meta.web_collaborator_id_set())}
                    if meta.web_collaborator_id_set()
                    else {}
                ),
                **({"pinned_at": meta.pinned_at} if meta.is_pinned else {}),
                **({"custom_title": meta.custom_title} if (meta.custom_title or "").strip() else {}),
            }
            for sid, meta in self._sessions.items()
        }
        self._index_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._index_mtime = self._index_mtime_on_disk()

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
            raw_images = item.get("images")
            images: list[str] = []
            if isinstance(raw_images, list):
                images = [str(path).strip() for path in raw_images if str(path).strip()]
            raw_files = item.get("files")
            files: list[dict[str, object]] = []
            if isinstance(raw_files, list):
                for entry in raw_files:
                    if isinstance(entry, dict) and str(entry.get("url") or "").strip():
                        files.append(entry)
            if role not in ("user", "assistant") or (not content.strip() and not images and not files):
                continue
            author_id = str(item.get("author_id") or item.get("authorId") or "").strip()
            author_label = str(item.get("author_label") or item.get("authorLabel") or "").strip()
            messages.append(
                ChatMessage(
                    role=role,
                    content=content,
                    timestamp=str(item.get("timestamp") or _now_iso()),
                    images=images,
                    files=files,
                    author_id=author_id,
                    author_label=author_label,
                )
            )
        return messages

    def _save_messages(self, session_id: str, messages: list[ChatMessage]) -> None:
        self._messages_dir.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp,
                **({"images": m.images} if m.images else {}),
                **({"files": m.files} if m.files else {}),
                **({"author_id": m.author_id} if m.author_id else {}),
                **({"author_label": m.author_label} if m.author_label else {}),
            }
            for m in messages
        ]
        self._messages_path(session_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_sessions(self, *, enrich_names: bool = True) -> list[SessionMeta]:
        with self._exclusive_index():
            self._reload_index_if_stale()
            dirty = False
            for meta in self._sessions.values():
                if meta.source != "dingtalk" or meta.dingtalk_owner_id:
                    continue
                owner_id = parse_dingtalk_user_id(meta.dingtalk_key)
                if owner_id:
                    meta.dingtalk_owner_id = owner_id
                    dirty = True
            items = list(self._sessions.values())
            reverted_custom_titles: set[str] = set()
            for meta in items:
                messages = self._load_messages(meta.id)
                if messages and _apply_message_derived_meta(
                    meta, messages, custom_title_touched=reverted_custom_titles
                ):
                    dirty = True
            items = [s for s in items if s.message_count > 0]
            if enrich_names and items:
                try:
                    from dingtalk_user_lookup import collect_all_staff_labels, enrich_session_owner_labels

                    if enrich_session_owner_labels(items):
                        dirty = True
                    known = collect_all_staff_labels(items)
                    for meta in items:
                        if meta.source != "web":
                            continue
                        uid = (meta.web_owner_id or "").strip()
                        if not uid:
                            continue
                        expected = (known.get(uid) or "").strip()
                        if expected and meta.web_owner_label != expected:
                            meta.web_owner_label = expected
                            dirty = True
                except Exception as exc:  # noqa: BLE001
                    logger.warning("补全钉钉用户姓名失败: %s", exc)
            if dirty:
                self._custom_title_touched.update(reverted_custom_titles)
                try:
                    self._save_index()
                finally:
                    for sid in reverted_custom_titles:
                        self._custom_title_touched.discard(sid)
        pinned = [s for s in items if s.is_pinned]
        unpinned = [s for s in items if not s.is_pinned]
        pinned.sort(key=lambda s: s.pinned_at)
        unpinned.sort(key=lambda s: s.updated_at, reverse=True)
        return pinned + unpinned

    def create_session(
        self,
        *,
        title: str = "新对话",
        owner_id: str = "",
        owner_label: str = "",
    ) -> SessionMeta:
        sid = uuid.uuid4().hex[:16]
        now = _now_iso()
        meta = SessionMeta(
            id=sid,
            title=title.strip() or "新对话",
            created_at=now,
            updated_at=now,
            web_owner_id=(owner_id or "").strip(),
            web_owner_label=(owner_label or "").strip(),
        )
        with self._exclusive_index():
            self._sessions[sid] = meta
            self._save_index()
        self._save_messages(sid, [])
        return meta

    def get_session(self, session_id: str) -> SessionMeta | None:
        with self._lock:
            self._reload_index_if_stale()
            return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        with self._exclusive_index():
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
            self._reload_index_if_stale()
            if session_id not in self._sessions:
                return []
        return self._load_messages(session_id)

    def get_or_create_dingtalk_session(
        self,
        *,
        dingtalk_key: str,
        label: str = "",
        title_hint: str = "",
        owner_id: str = "",
    ) -> SessionMeta:
        key = (dingtalk_key or "").strip()
        if not key:
            raise ValueError("dingtalk_key 不能为空")
        session_id = dingtalk_session_id(key)
        nick = (label or "").strip()
        uid = (owner_id or "").strip() or parse_dingtalk_user_id(key)
        with self._exclusive_index():
            meta = self._sessions.get(session_id)
            if meta is None:
                now = _now_iso()
                hint = (title_hint or "").strip()
                if hint:
                    title = hint[:40] + ("…" if len(hint) > 40 else "")
                elif nick:
                    title = f"钉钉 · {nick}"
                elif uid:
                    title = f"钉钉 · {uid[:12]}"
                else:
                    title = f"钉钉 · {key.rsplit(':', 1)[-1][:12]}"
                meta = SessionMeta(
                    id=session_id,
                    title=title,
                    created_at=now,
                    updated_at=now,
                    message_count=0,
                    source="dingtalk",
                    dingtalk_key=key,
                    dingtalk_label=nick,
                    dingtalk_owner_id=uid,
                )
                self._sessions[session_id] = meta
                self._save_index()
                self._save_messages(session_id, [])
            else:
                changed = False
                if nick and meta.dingtalk_label != nick:
                    meta.dingtalk_label = nick
                    changed = True
                if uid and not meta.dingtalk_owner_id:
                    meta.dingtalk_owner_id = uid
                    changed = True
                hint = (title_hint or "").strip()
                if hint:
                    new_title = _title_from_text(hint)
                    if meta.title != new_title:
                        meta.title = new_title
                        changed = True
                if changed:
                    self._save_index()
        return meta

    def append_message_if_new(self, session_id: str, role: str, content: str) -> ChatMessage | None:
        text = (content or "").strip()
        if not text or role not in ("user", "assistant"):
            return None
        with self._lock:
            self._reload_index_if_stale()
            meta = self._sessions.get(session_id)
            if meta is None:
                return None
            messages = self._load_messages(session_id)
            if messages and messages[-1].role == role and messages[-1].content == text:
                return None
        return self.append_message(session_id, role, text)

    def upsert_dingtalk_turn(
        self, session_id: str, user_prompt: str, assistant_reply: str
    ) -> bool:
        """写入或更新一轮钉钉对话；同 prompt 重试时覆盖上一条 assistant。"""
        prompt = (user_prompt or "").strip()
        reply = (assistant_reply or "").strip()
        if not prompt or not reply:
            return False
        with self._exclusive_index():
            meta = self._sessions.get(session_id)
            if meta is None:
                return False
            messages = self._load_messages(session_id)

            if _turn_already_synced(messages, prompt, reply):
                return False

            reverted_custom_titles: set[str] = set()
            if messages and messages[-1].role == "assistant":
                for msg in reversed(messages[:-1]):
                    if msg.role == "user" and msg.content == prompt:
                        messages[-1] = ChatMessage(role="assistant", content=reply)
                        self._save_messages(session_id, messages)
                        _apply_message_derived_meta(
                            meta, messages, custom_title_touched=reverted_custom_titles
                        )
                        self._custom_title_touched.update(reverted_custom_titles)
                        try:
                            self._save_index()
                        finally:
                            for sid in reverted_custom_titles:
                                self._custom_title_touched.discard(sid)
                        return True
                    if msg.role == "user":
                        break

            if not (
                messages
                and messages[-1].role == "user"
                and messages[-1].content == prompt
            ):
                messages.append(ChatMessage(role="user", content=prompt))
            messages.append(ChatMessage(role="assistant", content=reply))
            self._save_messages(session_id, messages)
            _apply_message_derived_meta(
                meta, messages, custom_title_touched=reverted_custom_titles
            )
            self._custom_title_touched.update(reverted_custom_titles)
            try:
                self._save_index()
            finally:
                for sid in reverted_custom_titles:
                    self._custom_title_touched.discard(sid)
        return True

    def ensure_web_owner(
        self,
        session_id: str,
        *,
        owner_id: str = "",
        owner_label: str = "",
    ) -> bool:
        """首次写入网页会话归属；已有归属则不再变更。"""
        uid = (owner_id or "").strip()
        label = (owner_label or "").strip()
        if not uid:
            return False
        with self._exclusive_index():
            meta = self._sessions.get(session_id)
            if meta is None or meta.source != "web":
                return False
            if (meta.web_owner_id or "").strip():
                return False
            meta.web_owner_id = uid
            if label:
                meta.web_owner_label = label
            self._save_index()
        return True

    def set_session_pinned(
        self,
        session_id: str,
        *,
        pinned: bool,
    ) -> tuple[bool, str]:
        """设置会话置顶（全局可见，落盘共享）。"""
        with self._exclusive_index():
            meta = self._sessions.get(session_id)
            if meta is None:
                return False, "session not found"
            self._pinned_touched.add(session_id)
            try:
                meta.pinned_at = _now_iso() if pinned else ""
                self._save_index()
            finally:
                self._pinned_touched.discard(session_id)
        return True, ""

    def set_session_custom_title(
        self,
        session_id: str,
        *,
        title: str,
    ) -> tuple[bool, str]:
        """设置会话外显标题；空字符串表示恢复为自动标题。"""
        with self._exclusive_index():
            meta = self._sessions.get(session_id)
            if meta is None:
                return False, "session not found"
            messages = self._load_messages(session_id)
            reverted_custom_titles: set[str] = set()
            if messages:
                _apply_message_derived_meta(
                    meta, messages, custom_title_touched=reverted_custom_titles
                )
            self._custom_title_touched.update(reverted_custom_titles)
            self._custom_title_touched.add(session_id)
            try:
                meta.custom_title = _normalize_custom_title(title)
                self._save_index()
            finally:
                self._custom_title_touched.discard(session_id)
                for sid in reverted_custom_titles:
                    self._custom_title_touched.discard(sid)
        return True, ""

    def set_web_collaborators(
        self,
        session_id: str,
        *,
        owner_id: str,
        collaborator_ids: list[str],
    ) -> tuple[bool, str]:
        """会话拥有者设置共同对话成员。"""
        uid = (owner_id or "").strip()
        if not uid:
            return False, "missing owner"
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in collaborator_ids:
            staff_id = str(raw or "").strip()
            if not staff_id or staff_id == uid or staff_id in seen:
                continue
            seen.add(staff_id)
            normalized.append(staff_id)
        with self._exclusive_index():
            meta = self._sessions.get(session_id)
            if meta is None:
                return False, "session not found"
            if meta.source != "web":
                return False, "only web sessions support collaborators"
            session_owner = (meta.web_owner_id or "").strip()
            if not session_owner:
                return False, "session owner not set"
            if session_owner != uid:
                return False, "forbidden"
            meta.web_collaborator_ids = normalized
            self._save_index()
        return True, ""

    def is_read_only_for_viewer(
        self,
        session_id: str,
        viewer_staff_id: str | None = None,
    ) -> bool:
        with self._lock:
            self._reload_index_if_stale()
            meta = self._sessions.get(session_id)
        if meta is None:
            return True
        return meta.is_read_only_for_viewer(viewer_staff_id)

    def is_read_only(self, session_id: str) -> bool:
        """兼容旧调用：未提供 viewer 时，有归属的网页会话视为只读。"""
        return self.is_read_only_for_viewer(session_id, viewer_staff_id=None)

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        images: list[str] | None = None,
        files: list[dict[str, object]] | None = None,
        author_id: str = "",
        author_label: str = "",
    ) -> ChatMessage | None:
        text = (content or "").strip()
        image_list = [path.strip() for path in (images or []) if str(path).strip()]
        file_list = [entry for entry in (files or []) if isinstance(entry, dict)]
        if not text and not image_list and not file_list:
            return None
        with self._exclusive_index():
            meta = self._sessions.get(session_id)
            if meta is None:
                return None
            messages = self._load_messages(session_id)
            msg = ChatMessage(
                role=role,
                content=text,
                images=image_list,
                files=file_list,
                author_id=(author_id or "").strip(),
                author_label=(author_label or "").strip(),
            )
            messages.append(msg)
            self._save_messages(session_id, messages)
            reverted_custom_titles: set[str] = set()
            _apply_message_derived_meta(
                meta, messages, custom_title_touched=reverted_custom_titles
            )
            self._custom_title_touched.update(reverted_custom_titles)
            try:
                self._save_index()
            finally:
                for sid in reverted_custom_titles:
                    self._custom_title_touched.discard(sid)
        return msg

    def user_key(self, session_id: str) -> str:
        return f"web:{session_id}"


_STORE: WebSessionStore | None = None


def get_session_store() -> WebSessionStore:
    global _STORE
    if _STORE is None:
        _STORE = WebSessionStore()
    return _STORE
