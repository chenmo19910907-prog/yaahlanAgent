"""Web Agent Open API：Bearer 鉴权，契约对齐服务端 Agent /api/open/v1。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

WEB_AGENT_DIR = Path(__file__).resolve().parent
TASK_DIR = WEB_AGENT_DIR / "data" / "open_api_tasks"

SUBMIT_PATH = "/api/open/v1/task/submit"
QUERY_PATH = "/api/open/v1/task/query"

TOKEN_ENV_KEYS = (
    "YAAHLAN_WEB_AGENT_OPEN_API_TOKEN",
    "WEB_AGENT_OPEN_API_TOKEN",
)

_TASK_ID_PATTERN = re.compile(r"^[a-f0-9]{8,32}$")


def _load_env() -> None:
    gateway_dir = WEB_AGENT_DIR.parent / "dingtalk_gateway"
    if str(gateway_dir) not in sys.path:
        sys.path.insert(0, str(gateway_dir))
    from env_loader import load_env_local

    load_env_local()


def resolve_open_api_token() -> str:
    _load_env()
    for key in TOKEN_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def client_key_from_token(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return digest[:32]


def parse_bearer_token(handler: BaseHTTPRequestHandler) -> str:
    raw = (handler.headers.get("Authorization") or "").strip()
    if not raw.lower().startswith("bearer "):
        return ""
    return raw[7:].strip()


def authenticate(handler: BaseHTTPRequestHandler) -> tuple[str | None, dict[str, Any] | None, int]:
    """返回 (client_key, error_envelope, http_status)。"""
    configured = resolve_open_api_token()
    if not configured:
        return (
            None,
            envelope("CONFIG_ERROR", "未配置 Web Agent Open API Token（WEB_AGENT_OPEN_API_TOKEN）"),
            int(HTTPStatus.SERVICE_UNAVAILABLE),
        )
    presented = parse_bearer_token(handler)
    if not presented:
        return (
            None,
            envelope("UNAUTHORIZED", "缺少 Authorization: Bearer <token>"),
            int(HTTPStatus.UNAUTHORIZED),
        )
    if not _secrets_equal(presented, configured):
        return (
            None,
            envelope("UNAUTHORIZED", "Token 无效"),
            int(HTTPStatus.UNAUTHORIZED),
        )
    return client_key_from_token(presented), None, 200


def _secrets_equal(a: str, b: str) -> bool:
    try:
        import hmac

        return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
    except (TypeError, ValueError):
        return False


def envelope(code: str, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": code,
        "message": message or "",
        "data": data if isinstance(data, dict) else {},
    }
    return payload


def open_api_owner_id(client_key: str) -> str:
    key = (client_key or "").strip()
    return f"openapi:{key[:16]}" if key else "openapi:anonymous"


def open_api_owner_label() -> str:
    return "Open API"


@dataclass(frozen=True)
class OpenApiTaskRecord:
    task_id: str
    run_id: str
    session_id: str
    client_key: str
    message_preview: str
    created_at: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "client_key": self.client_key,
            "message_preview": self.message_preview,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OpenApiTaskRecord:
        return cls(
            task_id=str(data.get("task_id") or ""),
            run_id=str(data.get("run_id") or data.get("task_id") or ""),
            session_id=str(data.get("session_id") or ""),
            client_key=str(data.get("client_key") or ""),
            message_preview=str(data.get("message_preview") or ""),
            created_at=float(data.get("created_at") or 0.0),
        )


def _task_path(task_id: str) -> Path:
    if not _TASK_ID_PATTERN.match(task_id):
        raise ValueError("invalid task_id")
    return TASK_DIR / f"{task_id}.json"


def register_open_api_task(record: OpenApiTaskRecord) -> None:
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    _task_path(record.task_id).write_text(
        json.dumps(record.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_open_api_task(task_id: str) -> OpenApiTaskRecord | None:
    task_id = (task_id or "").strip()
    if not task_id or not _TASK_ID_PATTERN.match(task_id):
        return None
    path = _task_path(task_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return OpenApiTaskRecord.from_dict(data)


def message_preview(text: str, *, limit: int = 48) -> str:
    line = " ".join((text or "").split())
    if not line:
        return "Open API 对话"
    if len(line) <= limit:
        return line
    return line[: limit - 1] + "…"


def map_run_status_to_open_api(run_status: str) -> str:
    status = (run_status or "").strip().lower()
    if status == "done":
        return "completed"
    if status == "error":
        return "failed"
    if status == "interrupted":
        return "cancelled"
    if status == "running":
        return "running"
    return "pending"


def build_task_query_data(
    *,
    task_id: str,
    session_id: str,
    run_status: str,
    final_text: str,
    error_text: str | None,
) -> dict[str, Any]:
    api_status = map_run_status_to_open_api(run_status)
    data: dict[str, Any] = {
        "task_id": task_id,
        "conversation_id": session_id,
        "status": api_status,
    }
    if api_status == "completed":
        data["result"] = (final_text or "").strip()
    elif api_status == "failed":
        data["error_message"] = (error_text or final_text or "任务失败").strip()
    elif api_status == "cancelled":
        data["error_message"] = (error_text or "任务已取消").strip()
    return data


def is_open_api_path(path: str) -> bool:
    p = (path or "").rstrip("/")
    return p in (SUBMIT_PATH, QUERY_PATH)
