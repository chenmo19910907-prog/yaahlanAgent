"""Web Agent Open API：管理员个人 Token（哈希落库，明文仅生成时返回一次）。"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Any

WEB_AGENT_DIR = Path(__file__).resolve().parent
USER_TOKENS_PATH = WEB_AGENT_DIR / "data" / "open_api_user_tokens.json"

TOKEN_PREFIX = "ywa_"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _load_store() -> dict[str, Any]:
    if not USER_TOKENS_PATH.is_file():
        return {}
    try:
        data = json.loads(USER_TOKENS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_store(store: dict[str, Any]) -> None:
    USER_TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_TOKENS_PATH.write_text(
        json.dumps(store, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def token_preview(token: str) -> str:
    raw = (token or "").strip()
    if len(raw) <= 12:
        return raw
    return f"{raw[:8]}…{raw[-4:]}"


def has_any_user_tokens() -> bool:
    store = _load_store()
    users = store.get("users")
    return isinstance(users, dict) and bool(users)


def user_token_status(staff_id: str) -> dict[str, Any]:
    sid = (staff_id or "").strip()
    store = _load_store()
    users = store.get("users") if isinstance(store.get("users"), dict) else {}
    row = users.get(sid) if isinstance(users, dict) else None
    if not isinstance(row, dict):
        return {"hasToken": False, "tokenPreview": "", "updatedAt": None}
    preview = str(row.get("token_preview") or "").strip()
    updated = row.get("updated_at")
    try:
        updated_at = float(updated) if updated is not None else None
    except (TypeError, ValueError):
        updated_at = None
    return {
        "hasToken": bool(row.get("token_hash")),
        "tokenPreview": preview,
        "updatedAt": updated_at,
    }


def generate_user_token(staff_id: str) -> tuple[str, dict[str, Any]]:
    sid = (staff_id or "").strip()
    if not sid:
        raise ValueError("staff_id 必填")
    plaintext = TOKEN_PREFIX + secrets.token_urlsafe(32)
    preview = token_preview(plaintext)
    now = time.time()
    store = _load_store()
    users = store.get("users")
    if not isinstance(users, dict):
        users = {}
    existing = users.get(sid)
    created_at = now
    if isinstance(existing, dict) and existing.get("created_at") is not None:
        try:
            created_at = float(existing["created_at"])
        except (TypeError, ValueError):
            created_at = now
    users[sid] = {
        "token_hash": _hash_token(plaintext),
        "token_preview": preview,
        "created_at": created_at,
        "updated_at": now,
    }
    store["users"] = users
    _save_store(store)
    return plaintext, {
        "hasToken": True,
        "tokenPreview": preview,
        "updatedAt": now,
        "regenerated": True,
    }


def resolve_staff_id_from_user_token(presented: str) -> str | None:
    token = (presented or "").strip()
    if not token:
        return None
    digest = _hash_token(token)
    store = _load_store()
    users = store.get("users")
    if not isinstance(users, dict):
        return None
    for staff_id, row in users.items():
        if not isinstance(row, dict):
            continue
        if row.get("token_hash") == digest:
            return str(staff_id).strip() or None
    return None
