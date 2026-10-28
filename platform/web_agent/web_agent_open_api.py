"""Web Agent Open API：Bearer 鉴权，契约对齐服务端 Agent /api/open/v1。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

OPEN_API_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
OPEN_API_QUERY_RETRY_AFTER_MS = 2000
OPEN_API_PROGRESS_PREVIEW_LIMIT = 240

CALLBACK_SECRET_ENV_KEYS = (
    "YAAHLAN_WEB_AGENT_OPEN_API_CALLBACK_SECRET",
    "WEB_AGENT_OPEN_API_CALLBACK_SECRET",
)

WEB_AGENT_DIR = Path(__file__).resolve().parent
TASK_DIR = WEB_AGENT_DIR / "data" / "open_api_tasks"

SUBMIT_PATH = "/api/open/v1/task/submit"
QUERY_PATH = "/api/open/v1/task/query"

OPEN_API_MESSAGE_SOURCE_TAG = "API"

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


STAFF_CLIENT_KEY_PREFIX = "openapi:staff:"


def client_key_from_token(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return digest[:32]


def client_key_for_staff(staff_id: str) -> str:
    sid = (staff_id or "").strip()
    return f"{STAFF_CLIENT_KEY_PREFIX}{sid}" if sid else ""


def staff_id_from_client_key(client_key: str) -> str | None:
    key = (client_key or "").strip()
    if not key.startswith(STAFF_CLIENT_KEY_PREFIX):
        return None
    sid = key[len(STAFF_CLIENT_KEY_PREFIX) :].strip()
    return sid or None


def parse_bearer_token(handler: BaseHTTPRequestHandler) -> str:
    raw = (handler.headers.get("Authorization") or "").strip()
    if not raw.lower().startswith("bearer "):
        return ""
    return raw[7:].strip()


def authenticate(handler: BaseHTTPRequestHandler) -> tuple[str | None, dict[str, Any] | None, int]:
    """返回 (client_key, error_envelope, http_status)。"""
    from web_agent_open_api_user_tokens import (  # noqa: WPS433
        has_any_user_tokens,
        resolve_staff_id_from_user_token,
    )

    presented = parse_bearer_token(handler)
    if not presented:
        return (
            None,
            envelope("UNAUTHORIZED", "缺少 Authorization: Bearer <token>"),
            int(HTTPStatus.UNAUTHORIZED),
        )
    configured = resolve_open_api_token()
    if configured and _secrets_equal(presented, configured):
        return client_key_from_token(presented), None, 200

    staff_id = resolve_staff_id_from_user_token(presented)
    if staff_id:
        return client_key_for_staff(staff_id), None, 200

    if not configured and not has_any_user_tokens():
        return (
            None,
            envelope("CONFIG_ERROR", "未配置 Web Agent Open API Token（WEB_AGENT_OPEN_API_TOKEN）"),
            int(HTTPStatus.SERVICE_UNAVAILABLE),
        )
    return (
        None,
        envelope("UNAUTHORIZED", "Token 无效"),
        int(HTTPStatus.UNAUTHORIZED),
    )


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
    staff_id = staff_id_from_client_key(client_key)
    if staff_id:
        return staff_id
    key = (client_key or "").strip()
    return f"openapi:{key[:16]}" if key else "openapi:anonymous"


def open_api_owner_label(client_key: str) -> str:
    staff_id = staff_id_from_client_key(client_key)
    if not staff_id:
        return "Open API"
    try:
        from dingtalk_user_lookup import lookup_auth_user_display_name

        return lookup_auth_user_display_name(staff_id, "") or staff_id
    except Exception:  # noqa: BLE001
        return staff_id


@dataclass(frozen=True)
class OpenApiSubmitIdentity:
    """Open API 提交时的会话归属与 Agent 调用人上下文。"""

    owner_id: str
    owner_label: str
    session_client_key: str
    caller_momoid: str = ""


def _parse_caller_from_body(body: dict[str, Any]) -> tuple[str, str, str]:
    caller = body.get("caller")
    if not isinstance(caller, dict):
        caller = {}
    work_id = str(
        caller.get("work_id")
        or caller.get("workId")
        or body.get("work_id")
        or body.get("caller_work_id")
        or ""
    ).strip()
    name = str(caller.get("name") or body.get("caller_name") or "").strip()
    momoid = str(caller.get("momoid") or body.get("momoid") or "").strip()
    return work_id, name, momoid


def resolve_submit_identity(body: dict[str, Any], client_key: str) -> OpenApiSubmitIdentity:
    """不传 caller 时会话归属 Token 提供者；个人 Token 绑定钉钉 staff_id；服务 Token 可传 caller.work_id。"""
    key = (client_key or "").strip()
    default_owner_id = open_api_owner_id(key)
    default_owner_label = open_api_owner_label(key)
    work_id, name, momoid = _parse_caller_from_body(body if isinstance(body, dict) else {})

    staff_from_token = staff_id_from_client_key(key)
    if staff_from_token:
        owner_id = staff_from_token
        owner_label = name or default_owner_label
        session_key = key
    elif work_id:
        owner_id = work_id
        owner_label = name or work_id
        session_key = client_key_for_staff(work_id)
    else:
        owner_id = default_owner_id
        owner_label = default_owner_label
        session_key = key

    return OpenApiSubmitIdentity(
        owner_id=owner_id,
        owner_label=owner_label,
        session_client_key=session_key,
        caller_momoid=momoid,
    )


@dataclass(frozen=True)
class OpenApiTaskRecord:
    task_id: str
    run_id: str
    session_id: str
    client_key: str
    message_preview: str
    created_at: float
    callback_url: str = ""
    callback_dispatched: bool = False

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "client_key": self.client_key,
            "message_preview": self.message_preview,
            "created_at": self.created_at,
        }
        if self.callback_url:
            payload["callback_url"] = self.callback_url
        if self.callback_dispatched:
            payload["callback_dispatched"] = True
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OpenApiTaskRecord:
        return cls(
            task_id=str(data.get("task_id") or ""),
            run_id=str(data.get("run_id") or data.get("task_id") or ""),
            session_id=str(data.get("session_id") or ""),
            client_key=str(data.get("client_key") or ""),
            message_preview=str(data.get("message_preview") or ""),
            created_at=float(data.get("created_at") or 0.0),
            callback_url=str(data.get("callback_url") or "").strip(),
            callback_dispatched=bool(data.get("callback_dispatched")),
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


def resolve_open_api_callback_secret() -> str:
    _load_env()
    for key in CALLBACK_SECRET_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    try:
        from service_agent_webhook import resolve_webhook_secret  # noqa: WPS433

        return resolve_webhook_secret()
    except Exception:  # noqa: BLE001
        return ""


def normalize_open_api_callback_url(raw: str) -> str | None:
    """校验 submit 中的 callback_url；不可达或非法 scheme 时返回 None。"""
    url = (raw or "").strip().rstrip("/")
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not (parsed.hostname or "").strip():
        return None
    try:
        from service_agent_webhook import callback_url_reachable  # noqa: WPS433

        if not callback_url_reachable(url):
            return None
    except Exception:  # noqa: BLE001
        return None
    return url


def mark_open_api_callback_dispatched(task_id: str) -> None:
    task_id = (task_id or "").strip()
    if not task_id or not _TASK_ID_PATTERN.match(task_id):
        return
    path = _task_path(task_id)
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    data["callback_dispatched"] = True
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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


def parse_open_api_submit_attachment_items(body: dict[str, Any]) -> list[dict[str, str]]:
    """解析 submit 请求中的 images / attachments，格式与 POST /api/chat 一致。"""
    if not isinstance(body, dict):
        return []
    raw_attachments = body.get("attachments")
    if not isinstance(raw_attachments, list):
        raw_attachments = []
    legacy_images = body.get("images")
    if isinstance(legacy_images, list):
        for item in legacy_images:
            if isinstance(item, dict):
                raw_attachments.append(item)
    items: list[dict[str, str]] = []
    for item in raw_attachments:
        if isinstance(item, dict):
            items.append(item)
    return items


def submit_title_hint(message: str, attachment_items: list[dict[str, str]]) -> str:
    text = (message or "").strip()
    if text:
        return message_preview(text)
    count = len(attachment_items)
    if count:
        return message_preview(f"[附带 {count} 个附件]")
    return message_preview("")


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


def progress_preview(text: str, *, limit: int = OPEN_API_PROGRESS_PREVIEW_LIMIT) -> str:
    line = " ".join((text or "").split())
    if not line:
        return ""
    if len(line) <= limit:
        return line
    return line[: limit - 1] + "…"


def build_task_query_data(
    *,
    task_id: str,
    session_id: str,
    run_status: str,
    final_text: str,
    error_text: str | None,
    phase_line: str = "",
    last_markdown: str = "",
) -> dict[str, Any]:
    api_status = map_run_status_to_open_api(run_status)
    data: dict[str, Any] = {
        "task_id": task_id,
        "conversation_id": session_id,
        "status": api_status,
    }
    phase = (phase_line or "").strip()
    if phase and api_status in {"pending", "running"}:
        data["phase"] = phase
    preview = progress_preview(last_markdown)
    if preview and api_status in {"pending", "running"}:
        data["progress_preview"] = preview
    if api_status in {"pending", "running"}:
        data["retry_after_ms"] = OPEN_API_QUERY_RETRY_AFTER_MS
    if api_status == "completed":
        data["result"] = (final_text or "").strip()
    elif api_status == "failed":
        data["error_message"] = (error_text or final_text or "任务失败").strip()
    elif api_status == "cancelled":
        data["error_message"] = (error_text or "任务已取消").strip()
    return data


def build_task_query_data_for_run(task_id: str) -> dict[str, Any] | None:
    """从 run 存储组装 query data；task 索引缺失时仍可按 run_id 查询。"""
    task_id = (task_id or "").strip()
    if not task_id:
        return None
    from web_run_store import get_run_store  # noqa: WPS433

    run_store = get_run_store()
    meta = run_store.get_run(task_id)
    if meta is None:
        return None
    snap = run_store.get_snapshot(task_id)
    return build_task_query_data(
        task_id=task_id,
        session_id=meta.session_id,
        run_status=meta.status,
        final_text=snap.final_text,
        error_text=snap.error,
        phase_line=snap.last_phase_line,
        last_markdown=snap.last_markdown,
    )


def _post_open_api_callback(url: str, envelope: dict[str, Any]) -> bool:
    body_bytes = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    secret = resolve_open_api_callback_secret()
    if secret:
        from service_agent_webhook import SIGNATURE_HEADER, compute_webhook_signature  # noqa: WPS433

        headers[SIGNATURE_HEADER] = compute_webhook_signature(body_bytes, secret)
    request = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response.read(256)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("Open API callback 失败 task_url=%s: %s", url, exc)
        return False
    return True


def _dispatch_open_api_callback(task_id: str) -> None:
    record = get_open_api_task(task_id)
    if record is None or not record.callback_url or record.callback_dispatched:
        return
    data = build_task_query_data_for_run(task_id)
    if data is None:
        return
    if str(data.get("status") or "") not in OPEN_API_TERMINAL_STATUSES:
        return
    envelope_payload = envelope("OK", "", data)
    if not _post_open_api_callback(record.callback_url, envelope_payload):
        return
    mark_open_api_callback_dispatched(task_id)


def schedule_open_api_callback(task_id: str) -> None:
    """任务终态时异步 POST callback_url（幂等）。"""
    task_id = (task_id or "").strip()
    if not task_id:
        return
    threading.Thread(
        target=_dispatch_open_api_callback,
        args=(task_id,),
        daemon=True,
        name=f"open-api-cb-{task_id[:8]}",
    ).start()


def is_open_api_path(path: str) -> bool:
    p = (path or "").rstrip("/")
    return p in (SUBMIT_PATH, QUERY_PATH)
