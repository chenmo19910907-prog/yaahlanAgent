"""Web Agent 留言板：JSON 持久化，所有人可见全部留言，仅可删除自己的。"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WEB_AGENT_DIR = Path(__file__).resolve().parent
MESSAGE_BOARD_PATH = WEB_AGENT_DIR / "data" / "message_board.json"
MAX_CONTENT_LEN = 2000
MAX_MESSAGES = 500
GUEST_STAFF_PREFIX = "guest_"
GUEST_STAFF_PATTERN = r"^guest_[a-f0-9]{32}$"
_GUEST_ID_RE = re.compile(GUEST_STAFF_PATTERN)


def is_guest_staff_id(staff_id: str) -> bool:
    return bool(_GUEST_ID_RE.fullmatch((staff_id or "").strip()))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_message_board(path: Path | None = None) -> dict[str, Any]:
    target = path or MESSAGE_BOARD_PATH
    if not target.is_file():
        return {"messages": []}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"messages": []}
        messages = data.get("messages")
        if not isinstance(messages, list):
            return {"messages": []}
        return {"messages": messages}
    except (OSError, json.JSONDecodeError):
        return {"messages": []}


def save_message_board(data: dict[str, Any], path: Path | None = None) -> None:
    target = path or MESSAGE_BOARD_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _normalize_message(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    msg_id = str(raw.get("id") or "").strip()
    staff_id = str(raw.get("staffId") or "").strip()
    content = str(raw.get("content") or "").strip()
    if not msg_id or not staff_id or not content:
        return None
    display_name = str(raw.get("displayName") or "").strip()
    created_at = str(raw.get("createdAt") or "").strip() or _utc_now_iso()
    return {
        "id": msg_id,
        "staffId": staff_id,
        "displayName": display_name,
        "content": content[:MAX_CONTENT_LEN],
        "showRealName": bool(raw.get("showRealName")),
        "createdAt": created_at,
    }


def normalize_guest_id(raw: Any) -> str | None:
    value = str(raw or "").strip()
    if not value or not _GUEST_ID_RE.fullmatch(value):
        return None
    return value


def normalize_create_payload(body: Any) -> tuple[str, bool] | None:
    if not isinstance(body, dict):
        return None
    content = str(body.get("content") or "").strip()
    if not content:
        return None
    if len(content) > MAX_CONTENT_LEN:
        content = content[:MAX_CONTENT_LEN]
    show_real_name = bool(body.get("showRealName"))
    return content, show_real_name


def create_message(
    *,
    staff_id: str,
    display_name: str,
    content: str,
    show_real_name: bool,
    path: Path | None = None,
) -> dict[str, Any]:
    uid = (staff_id or "").strip()
    if not uid:
        raise ValueError("missing staff_id")
    text = (content or "").strip()
    if not text:
        raise ValueError("empty content")
    if len(text) > MAX_CONTENT_LEN:
        text = text[:MAX_CONTENT_LEN]

    data = load_message_board(path)
    messages_raw = data.get("messages")
    messages: list[dict[str, Any]] = []
    if isinstance(messages_raw, list):
        for item in messages_raw:
            normalized = _normalize_message(item)
            if normalized is not None:
                messages.append(normalized)

    created = {
        "id": uuid.uuid4().hex,
        "staffId": uid,
        "displayName": (display_name or uid).strip(),
        "content": text,
        "showRealName": bool(show_real_name),
        "createdAt": _utc_now_iso(),
    }
    messages.append(created)
    if len(messages) > MAX_MESSAGES:
        messages = messages[-MAX_MESSAGES:]
    save_message_board({"messages": messages}, path)
    return created


def _author_label(
    msg: dict[str, Any],
    *,
    viewer_staff_id: str,
    is_admin: bool,
) -> str:
    staff_id = str(msg.get("staffId") or "").strip()
    if is_guest_staff_id(staff_id):
        return "访客"
    is_mine = staff_id == viewer_staff_id
    display_name = str(msg.get("displayName") or staff_id or "").strip()
    if msg.get("showRealName"):
        return display_name or "用户"
    if is_mine:
        return "匿名（我）"
    return "匿名"


def message_to_public(
    msg: dict[str, Any],
    *,
    viewer_staff_id: str,
    is_admin: bool,
) -> dict[str, Any]:
    staff_id = str(msg.get("staffId") or "").strip()
    is_mine = staff_id == viewer_staff_id
    is_guest_author = is_guest_staff_id(staff_id)
    payload: dict[str, Any] = {
        "id": msg["id"],
        "content": msg["content"],
        "showRealName": bool(msg.get("showRealName")),
        "authorLabel": _author_label(msg, viewer_staff_id=viewer_staff_id, is_admin=is_admin),
        "createdAt": msg.get("createdAt") or "",
        "isMine": is_mine,
        "isGuestAuthor": is_guest_author,
        "canDelete": is_mine,
    }
    if is_admin:
        payload["staffId"] = msg.get("staffId") or ""
    return payload


def list_messages_for_viewer(
    *,
    viewer_staff_id: str,
    is_admin: bool,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    viewer = (viewer_staff_id or "").strip()
    if not viewer:
        return []

    data = load_message_board(path)
    messages_raw = data.get("messages")
    if not isinstance(messages_raw, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in messages_raw:
        msg = _normalize_message(item)
        if msg is None:
            continue
        normalized.append(msg)

    normalized.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    return [
        message_to_public(msg, viewer_staff_id=viewer, is_admin=is_admin)
        for msg in normalized
    ]


def delete_message(
    *,
    message_id: str,
    viewer_staff_id: str,
    is_admin: bool,
    path: Path | None = None,
) -> bool:
    target_id = (message_id or "").strip()
    viewer = (viewer_staff_id or "").strip()
    if not target_id or not viewer:
        return False

    data = load_message_board(path)
    messages_raw = data.get("messages")
    if not isinstance(messages_raw, list):
        return False

    messages: list[dict[str, Any]] = []
    removed = False
    for item in messages_raw:
        msg = _normalize_message(item)
        if msg is None:
            continue
        if msg.get("id") == target_id:
            if msg.get("staffId") != viewer:
                raise PermissionError("无权删除该反馈")
            removed = True
            continue
        messages.append(msg)

    if not removed:
        return False
    save_message_board({"messages": messages}, path)
    return True
