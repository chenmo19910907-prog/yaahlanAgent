"""按用户存储 Cursor Dashboard 会话凭据（WorkosCursorSessionToken / email）。"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("web-agent")

WEB_AGENT_DIR = Path(__file__).resolve().parent
STORE_PATH = WEB_AGENT_DIR / "data" / "cursor_usage_credentials.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CursorUsageCredentialStore:
    def __init__(self, path: Path = STORE_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()

    def _load(self) -> dict[str, dict[str, str]]:
        if not self._path.is_file():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取 Cursor 用量凭据失败: %s", exc)
            return {}
        users = raw.get("users") if isinstance(raw, dict) else None
        if not isinstance(users, dict):
            return {}
        out: dict[str, dict[str, str]] = {}
        for staff_id, item in users.items():
            if not isinstance(item, dict):
                continue
            sid = str(staff_id or "").strip()
            if not sid:
                continue
            out[sid] = {
                "sessionToken": str(item.get("sessionToken") or "").strip(),
                "cursorEmail": str(item.get("cursorEmail") or "").strip(),
                "teamId": str(item.get("teamId") or "").strip(),
                "workosId": str(item.get("workosId") or "").strip(),
                "updatedAt": str(item.get("updatedAt") or "").strip(),
            }
        return out

    def _save(self, users: dict[str, dict[str, str]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"users": users}
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_credentials(self, staff_id: str) -> dict[str, str]:
        sid = (staff_id or "").strip()
        if not sid:
            return {"sessionToken": "", "cursorEmail": "", "teamId": "", "workosId": "", "updatedAt": ""}
        with self._lock:
            row = self._load().get(sid, {})
        return {
            "sessionToken": str(row.get("sessionToken") or "").strip(),
            "cursorEmail": str(row.get("cursorEmail") or "").strip(),
            "teamId": str(row.get("teamId") or "").strip(),
            "workosId": str(row.get("workosId") or "").strip(),
            "updatedAt": str(row.get("updatedAt") or "").strip(),
        }

    def status_for_staff(self, staff_id: str) -> dict[str, Any]:
        creds = self.get_credentials(staff_id)
        return {
            "configured": bool(creds["sessionToken"] or creds["cursorEmail"]),
            "hasSessionToken": bool(creds["sessionToken"]),
            "hasCursorEmail": bool(creds["cursorEmail"]),
            "updatedAt": creds["updatedAt"] or None,
        }

    def upsert(
        self,
        staff_id: str,
        *,
        session_token: str | None = None,
        cursor_email: str | None = None,
        team_id: str | None = None,
        workos_id: str | None = None,
    ) -> dict[str, Any]:
        sid = (staff_id or "").strip()
        if not sid:
            raise ValueError("staff_id 不能为空")
        token = (session_token or "").strip() if session_token is not None else None
        email = (cursor_email or "").strip().lower() if cursor_email is not None else None
        team = (team_id or "").strip() if team_id is not None else None
        workos = (workos_id or "").strip() if workos_id is not None else None
        if email is not None and email and "@" not in email:
            raise ValueError("Cursor 邮箱格式无效")

        with self._lock:
            users = self._load()
            current = users.get(sid, {})
            next_row = {
                "sessionToken": current.get("sessionToken", ""),
                "cursorEmail": current.get("cursorEmail", ""),
                "teamId": current.get("teamId", ""),
                "workosId": current.get("workosId", ""),
                "updatedAt": _now_iso(),
            }
            if token is not None:
                next_row["sessionToken"] = token
            if email is not None:
                next_row["cursorEmail"] = email
            if team is not None:
                next_row["teamId"] = team
            if workos is not None:
                next_row["workosId"] = workos
            if not next_row["sessionToken"] and not next_row["cursorEmail"]:
                users.pop(sid, None)
            else:
                users[sid] = next_row
            self._save(users)
        return self.status_for_staff(sid)

    def clear(self, staff_id: str) -> dict[str, Any]:
        sid = (staff_id or "").strip()
        if not sid:
            return {"configured": False, "hasSessionToken": False, "hasCursorEmail": False}
        with self._lock:
            users = self._load()
            users.pop(sid, None)
            self._save(users)
        return self.status_for_staff(sid)


_STORE: CursorUsageCredentialStore | None = None


def get_cursor_usage_store() -> CursorUsageCredentialStore:
    global _STORE
    if _STORE is None:
        _STORE = CursorUsageCredentialStore()
    return _STORE
