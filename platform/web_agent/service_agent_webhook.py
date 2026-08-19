"""服务端 Agent Open API Webhook：验签、回调接收与任务等待。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import socket
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

WEB_AGENT_DIR = Path(__file__).resolve().parent
PUBLIC_URL_FILE = WEB_AGENT_DIR / "data" / "public_url.txt"
WEBHOOK_DATA_DIR = WEB_AGENT_DIR / "data" / "service_agent_webhook"
PENDING_DIR = WEBHOOK_DATA_DIR / "pending"
DONE_DIR = WEBHOOK_DATA_DIR / "done"

WEBHOOK_PATH = "/api/service-agent/webhook"
WEBHOOK_URL_ENV_KEYS = ("YAAHLAN_SERVICE_AGENT_WEBHOOK_URL", "SERVICE_AGENT_WEBHOOK_URL")
WEBHOOK_SECRET_ENV_KEYS = (
    "YAAHLAN_SERVICE_AGENT_WEBHOOK_SECRET",
    "SERVICE_AGENT_WEBHOOK_SECRET",
)
USE_WEBHOOK_ENV_KEYS = ("YAAHLAN_SERVICE_AGENT_USE_WEBHOOK", "SERVICE_AGENT_USE_WEBHOOK")

SIGNATURE_HEADER = "X-Webhook-Signature"
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def _load_env() -> None:
    gateway_dir = WEB_AGENT_DIR.parent / "dingtalk_gateway"
    if str(gateway_dir) not in sys.path:
        sys.path.insert(0, str(gateway_dir))
    from env_loader import load_env_local

    load_env_local()


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def resolve_webhook_secret(explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    _load_env()
    for key in WEBHOOK_SECRET_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def callback_url_reachable(url: str, *, timeout_s: float = 2.0) -> bool:
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").strip()
    if not host or parsed.scheme not in {"https", "http"}:
        return False
    try:
        socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except OSError:
        return False
    return True


def resolve_callback_url(explicit: str | None = None) -> str | None:
    if explicit is not None:
        value = explicit.strip()
        if not value:
            return None
        return value.rstrip("/") if callback_url_reachable(value) else None
    _load_env()
    for key in WEBHOOK_URL_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value and callback_url_reachable(value):
            return value.rstrip("/")
    if PUBLIC_URL_FILE.is_file():
        try:
            base = PUBLIC_URL_FILE.read_text(encoding="utf-8").strip().rstrip("/")
        except OSError:
            base = ""
        if base:
            candidate = f"{base}{WEBHOOK_PATH}"
            if callback_url_reachable(candidate):
                return candidate
    return None


def webhook_mode_enabled(
    *,
    secret: str | None = None,
    callback_url: str | None = None,
    explicit: bool | None = None,
) -> bool:
    if explicit is False:
        return False
    if explicit is True:
        return bool((secret or resolve_webhook_secret()) and (callback_url or resolve_callback_url()))
    _load_env()
    for key in USE_WEBHOOK_ENV_KEYS:
        if os.environ.get(key, "").strip():
            return _env_bool(key, True) and bool(
                (secret or resolve_webhook_secret()) and (callback_url or resolve_callback_url())
            )
    if not _env_bool("YAAHLAN_SERVICE_AGENT_USE_WEBHOOK", True):
        return False
    return bool((secret or resolve_webhook_secret()) and (callback_url or resolve_callback_url()))


def _safe_task_filename(task_id: str) -> str:
    task_id = (task_id or "").strip()
    if not task_id or not TASK_ID_PATTERN.fullmatch(task_id):
        raise ValueError(f"无效 task_id: {task_id!r}")
    return f"{task_id}.json"


def compute_webhook_signature(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_webhook_signature(body: bytes, signature_header: str, secret: str) -> bool:
    if not secret or not signature_header:
        return False
    provided = signature_header.strip()
    if provided.lower().startswith("sha256="):
        provided = provided.split("=", 1)[1].strip()
    expected_hex = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if hmac.compare_digest(provided.lower(), expected_hex.lower()):
        return True
    expected_b64 = base64.b64encode(
        hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode("ascii")
    return hmac.compare_digest(provided, expected_b64)


def _extract_webhook_payload(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    data = raw.get("data")
    if isinstance(data, dict):
        merged = dict(data)
        for key in ("task_id", "status", "request_id", "conversation_id"):
            if key in raw and key not in merged:
                merged[key] = raw[key]
        return merged
    return raw


def register_pending_task(task_id: str) -> None:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    path = PENDING_DIR / _safe_task_filename(task_id)
    path.write_text(
        json.dumps({"task_id": task_id, "registered_at": time.time()}, ensure_ascii=False),
        encoding="utf-8",
    )


def notify_task_webhook(task_id: str, status: str, payload: dict[str, Any]) -> bool:
    pending_path = PENDING_DIR / _safe_task_filename(task_id)
    if not pending_path.is_file():
        return False
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    done_path = DONE_DIR / _safe_task_filename(task_id)
    done_path.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "status": status,
                "payload": payload,
                "notified_at": time.time(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    try:
        pending_path.unlink(missing_ok=True)
    except OSError:
        pass
    return True


def peek_webhook_notification(task_id: str) -> str | None:
    done_path = DONE_DIR / _safe_task_filename(task_id)
    if not done_path.is_file():
        return None
    try:
        data = json.loads(done_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    status = str(data.get("status") or "").strip()
    return status or None


def wait_for_webhook(task_id: str, timeout_s: float) -> str | None:
    deadline = time.monotonic() + max(0.0, timeout_s)
    while time.monotonic() < deadline:
        status = peek_webhook_notification(task_id)
        if status:
            return status
        if timeout_s <= 0:
            return None
        time.sleep(min(0.25, max(0.05, deadline - time.monotonic())))
    return peek_webhook_notification(task_id)


def cleanup_task_wait(task_id: str) -> None:
    for directory in (PENDING_DIR, DONE_DIR):
        try:
            (directory / _safe_task_filename(task_id)).unlink(missing_ok=True)
        except (OSError, ValueError):
            pass


def handle_webhook_body(body_bytes: bytes, signature_header: str) -> tuple[int, dict[str, Any]]:
    secret = resolve_webhook_secret()
    if not secret:
        return 503, {"error": "webhook secret not configured"}
    if not verify_webhook_signature(body_bytes, signature_header, secret):
        return 401, {"error": "invalid signature"}

    try:
        raw = json.loads(body_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 400, {"error": "invalid json"}

    payload = _extract_webhook_payload(raw if isinstance(raw, dict) else {})
    task_id = str(payload.get("task_id") or "").strip()
    status = str(payload.get("status") or "").strip().lower()
    if not task_id:
        return 400, {"error": "missing task_id"}
    if not status:
        return 400, {"error": "missing status"}

    try:
        accepted = notify_task_webhook(task_id, status, payload)
    except ValueError as exc:
        return 400, {"error": str(exc)}

    return 200, {"ok": True, "accepted": accepted, "task_id": task_id, "status": status}
