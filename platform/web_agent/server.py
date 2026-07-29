#!/usr/bin/env python3
"""Web Agent HTTP 服务：托管 chat.html，提供聊天 API 与 SSE 流式输出。"""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import queue
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

WEB_AGENT_DIR = Path(__file__).resolve().parent
PLATFORM_DIR = WEB_AGENT_DIR.parent
REPO_ROOT = PLATFORM_DIR.parent


def _python_can_import_cursor_sdk(python: Path) -> bool:
    try:
        proc = subprocess.run(
            [str(python), "-c", "import cursor_sdk"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _resolve_python_executable() -> str:
    """优先已安装 cursor-sdk 的 venv，避免子进程 import 失败立即退出。"""
    candidates = (
        REPO_ROOT / ".venv" / "bin" / "python3",
        PLATFORM_DIR / "dingtalk_gateway" / ".venv" / "bin" / "python3",
    )
    fallback: str | None = None
    for path in candidates:
        if not path.is_file() or not os.access(path, os.X_OK):
            continue
        resolved = str(path)
        if _python_can_import_cursor_sdk(path):
            return resolved
        fallback = fallback or resolved
    return fallback or sys.executable
GATEWAY_DIR = PLATFORM_DIR / "dingtalk_gateway"
SCRIPTS_DIR = PLATFORM_DIR / "scripts"

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from chat_runner import run_web_chat  # noqa: E402
from cursor_runner import DEFAULT_MODEL, DEFAULT_TIMEOUT_S  # noqa: E402
from external_agent_config import (  # noqa: E402
    external_agents_from_config,
    resolve_enabled_external_agent_ids,
)
from batch_progress import (  # noqa: E402
    build_batch_progress_message,
    clear_batch_progress,
    read_batch_progress,
)
from duration_history import classify_task_kind, get_duration_store  # noqa: E402
from progress_message import (  # noqa: E402
    append_duration_footer,
    build_streaming_progress_status_line,
    build_task_ack_message,
    resolve_task_estimate_seconds,
)
from task_session import TaskInterrupted, TaskSession  # noqa: E402
from dingtalk_web_sync import sync_all_from_conversation_store  # noqa: E402
from web_file_store import (  # noqa: E402
    ALLOWED_EXTENSIONS,
    FileUploadError,
    MAX_ATTACHMENTS_PER_MESSAGE,
    MAX_FILE_BYTES,
    MAX_IMAGE_BYTES,
    StoredAttachment,
    consume_pending_outputs,
    content_type_for_path,
    local_path_from_api_path,
    output_display_name,
    resolve_output_file,
    resolve_upload_file,
    save_chat_attachments,
)
from web_session_store import get_session_store  # noqa: E402
from web_admin_permission import is_web_admin, web_admin_denial_message  # noqa: E402
from web_auth import authorize_request, auth_enabled, logout_current_session  # noqa: E402
from web_otp_auth import (  # noqa: E402
    WEB_LOGIN_PHRASE,
    current_web_user,
    get_web_otp_store,
    is_public_auth_path,
    otp_auth_enabled,
    set_session_cookie,
)
from web_dingtalk_oauth import (  # noqa: E402
    dingtalk_oauth_enabled,
    dingtalk_oauth_public_config,
    login_with_auth_code,
)
from web_favicon_proxy import fetch_favicon  # noqa: E402
from web_bookmark_metadata import resolve_bookmark_metadata  # noqa: E402
from bookmarks_store import (  # noqa: E402
    load_bookmarks as _load_bookmarks,
    merge_legacy_bookmarks,
    normalize_bookmarks_payload as _normalize_bookmarks_payload,
    save_bookmarks as _save_bookmarks,
)
from message_board_store import (  # noqa: E402
    create_message as _create_message_board_entry,
    delete_message as _delete_message_board_entry,
    list_messages_for_viewer as _list_message_board_entries,
    normalize_create_payload as _normalize_message_board_payload,
    normalize_guest_id as _normalize_message_board_guest_id,
)

logger = logging.getLogger("web-agent")

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 18766
CONFIG_PATH = WEB_AGENT_DIR / "config.json"
FAMILY_PK_EXPORTS_DIR = REPO_ROOT / "platform" / "family_pk_report" / "exports"
SHOWCASE_URL_PREFIX = "/family-pk-showcase"
SSE_POLL_S = 0.25
RUN_TTL_S = 3600
PROGRESS_TICK_S = 1.0
SESSION_ID_PATTERN = r"[a-z0-9]+"


def _load_config() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _bookmarks_auth_ok(handler: SimpleHTTPRequestHandler) -> tuple[bool, str | None]:
    if otp_auth_enabled() and current_web_user(handler) is None:
        return False, "请先登录后再保存快捷入口"
    return True, None


def _handle_bookmarks_save(handler: SimpleHTTPRequestHandler, body: Any) -> None:
    ok, err = _bookmarks_auth_ok(handler)
    if not ok:
        return _json_response(handler, {"error": err}, 401)
    normalized = _normalize_bookmarks_payload(body)
    if normalized is None:
        return _json_response(handler, {"error": "invalid bookmarks payload"}, 400)
    try:
        _save_bookmarks(normalized)
    except OSError as exc:
        logger.exception("保存 bookmarks.json 失败")
        return _json_response(handler, {"error": f"保存失败：{exc}"}, 500)
    return _json_response(handler, {"ok": True, "bookmarks": normalized})


def _handle_bookmarks_import_legacy(handler: SimpleHTTPRequestHandler, body: Any) -> None:
    ok, err = _bookmarks_auth_ok(handler)
    if not ok:
        return _json_response(handler, {"error": err}, 401)
    if not isinstance(body, dict):
        return _json_response(handler, {"error": "invalid json"}, 400)
    merged, added = merge_legacy_bookmarks(_load_bookmarks(), body)
    if not added:
        return _json_response(
            handler,
            {"ok": True, "bookmarks": merged, "imported": [], "imported_count": 0},
        )
    try:
        _save_bookmarks(merged)
    except OSError as exc:
        logger.exception("导入 legacy bookmarks 失败")
        return _json_response(handler, {"error": f"保存失败：{exc}"}, 500)
    return _json_response(
        handler,
        {
            "ok": True,
            "bookmarks": merged,
            "imported": added,
            "imported_count": len(added),
        },
    )


def _message_board_viewer(
    handler: SimpleHTTPRequestHandler,
    *,
    body: Any | None = None,
) -> tuple[str, str, bool, bool, str | None]:
    """返回 (staff_id, display_name, is_admin, is_guest, error)。"""
    user = current_web_user(handler)
    if user is not None:
        admin = is_web_admin(staff_id=user.staff_id)
        return user.staff_id, user.display_name or user.staff_id, admin, False, None

    guest_raw = handler.headers.get("X-Message-Board-Guest")
    if guest_raw is None and isinstance(body, dict):
        guest_raw = body.get("guestId")
    guest_id = _normalize_message_board_guest_id(guest_raw)
    if guest_id is None:
        return "", "", False, True, "缺少访客标识，请刷新页面后重试"
    return guest_id, "访客", False, True, None


def _handle_message_board_list(handler: SimpleHTTPRequestHandler) -> None:
    staff_id, _, admin, _, err = _message_board_viewer(handler)
    if err:
        return _json_response(handler, {"error": err}, 400)
    messages = _list_message_board_entries(
        viewer_staff_id=staff_id,
        is_admin=admin,
    )
    return _json_response(
        handler,
        {
            "messages": messages,
            "isAdmin": admin,
        },
    )


def _handle_message_board_create(handler: SimpleHTTPRequestHandler, body: Any) -> None:
    staff_id, display_name, admin, is_guest, err = _message_board_viewer(handler, body=body)
    if err:
        return _json_response(handler, {"error": err}, 400)
    parsed = _normalize_message_board_payload(body)
    if parsed is None:
        return _json_response(handler, {"error": "反馈内容不能为空"}, 400)
    content, show_real_name = parsed
    if is_guest:
        show_real_name = False
    try:
        created = _create_message_board_entry(
            staff_id=staff_id,
            display_name=display_name,
            content=content,
            show_real_name=show_real_name,
        )
    except ValueError as exc:
        return _json_response(handler, {"error": str(exc)}, 400)
    except OSError as exc:
        logger.exception("保存留言板失败")
        return _json_response(handler, {"error": f"保存失败：{exc}"}, 500)
    public = _list_message_board_entries(
        viewer_staff_id=staff_id,
        is_admin=admin,
    )
    created_public = next((item for item in public if item.get("id") == created.get("id")), None)
    return _json_response(
        handler,
        {
            "ok": True,
            "message": created_public or created,
            "isAdmin": admin,
        },
    )


def _handle_message_board_delete(handler: SimpleHTTPRequestHandler, message_id: str) -> None:
    staff_id, _, admin, _, err = _message_board_viewer(handler)
    if err:
        return _json_response(handler, {"error": err}, 400)
    try:
        removed = _delete_message_board_entry(
            message_id=message_id,
            viewer_staff_id=staff_id,
            is_admin=admin,
        )
    except PermissionError as exc:
        return _json_response(handler, {"error": str(exc)}, 403)
    except OSError as exc:
        logger.exception("删除留言板条目失败")
        return _json_response(handler, {"error": f"删除失败：{exc}"}, 500)
    if not removed:
        return _json_response(handler, {"error": "反馈不存在"}, 404)
    return _json_response(handler, {"ok": True})


def _agent_models_from_config(cfg: dict[str, Any] | None = None) -> list[dict[str, str]]:
    data = cfg if cfg is not None else _load_config()
    default_id = str(data.get("defaultAgentModel") or DEFAULT_MODEL)
    raw = data.get("agentModels")
    models: list[dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or "").strip()
            if not model_id:
                continue
            models.append(
                {
                    "id": model_id,
                    "label": str(item.get("label") or model_id).strip(),
                    "description": str(item.get("description") or "").strip(),
                }
            )
    if not models:
        models = [{"id": default_id, "label": default_id, "description": ""}]
    return models


def _default_agent_model(cfg: dict[str, Any] | None = None) -> str:
    data = cfg if cfg is not None else _load_config()
    default_id = str(data.get("defaultAgentModel") or DEFAULT_MODEL).strip()
    allowed = {item["id"] for item in _agent_models_from_config(data)}
    if default_id in allowed:
        return default_id
    return next(iter(allowed), DEFAULT_MODEL)


def _resolve_agent_model(raw: object, cfg: dict[str, Any] | None = None) -> str:
    data = cfg if cfg is not None else _load_config()
    allowed = {item["id"] for item in _agent_models_from_config(data)}
    default_id = _default_agent_model(data)
    model = str(raw or "").strip() or default_id
    if model not in allowed:
        return default_id
    return model


def _load_catalog_data() -> dict[str, Any]:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from generate_catalog import _load_catalog_data as load_data  # noqa: WPS433

    return load_data()


def _external_agents_meta(cfg: dict[str, Any] | None = None) -> list[dict[str, str | bool]]:
    return [
        {
            "id": str(item["id"]),
            "label": str(item.get("label") or item["id"]),
            "description": str(item.get("description") or ""),
            "url": str(item.get("url") or ""),
            "defaultEnabled": bool(item.get("defaultEnabled")),
        }
        for item in external_agents_from_config(cfg)
    ]


def _platform_meta() -> dict[str, int | str]:
    cfg = _load_config()
    title = str(cfg.get("title") or "Yaahlan 智能工具 Agent")
    subtitle = str(
        cfg.get("subtitle") or "钉钉 Agent · MOA/Admin 查数 · Tunnel 抓包 · Stage 送礼 · 用例生成"
    )

    mcp_count = 0
    mcp_example = REPO_ROOT / ".cursor" / "mcp.example.json"
    if mcp_example.is_file():
        try:
            data = json.loads(mcp_example.read_text(encoding="utf-8"))
            servers = data.get("mcpServers") or {}
            if isinstance(servers, dict):
                mcp_count = len(servers)
        except (OSError, json.JSONDecodeError):
            pass

    skills_count = len(list((REPO_ROOT / ".cursor" / "skills").glob("*/SKILL.md")))

    modules_count = 0
    capabilities_count = 0
    sources = PLATFORM_DIR / "config" / "sources.json"
    if sources.is_file():
        try:
            data = json.loads(sources.read_text(encoding="utf-8"))
            modules = data.get("modules") or []
            if isinstance(modules, list):
                modules_count = len(modules)
            for mod in modules if isinstance(modules, list) else []:
                registry = REPO_ROOT / str(mod.get("registry", ""))
                if registry.is_file():
                    reg = json.loads(registry.read_text(encoding="utf-8"))
                    items = reg.get("items") or reg.get("capabilities") or []
                    if isinstance(items, list):
                        capabilities_count += len(items)
        except (OSError, json.JSONDecodeError):
            pass

    return {
        "title": title,
        "subtitle": subtitle,
        "mcp_count": mcp_count,
        "skills_count": skills_count,
        "modules_count": modules_count,
        "capabilities_count": capabilities_count,
        "defaultAgentModel": _default_agent_model(cfg),
        "agentModels": _agent_models_from_config(cfg),
        "externalAgents": _external_agents_meta(cfg),
        "quickPrompts": cfg.get("quickPrompts") or [],
        "quickPromptCount": int(cfg.get("quickPromptCount") or 4),
        "bookmarks": _load_bookmarks(),
        "maxImagesPerMessage": MAX_ATTACHMENTS_PER_MESSAGE,
        "maxAttachmentsPerMessage": MAX_ATTACHMENTS_PER_MESSAGE,
        "maxImageBytes": MAX_IMAGE_BYTES,
        "maxFileBytes": MAX_FILE_BYTES,
        "allowedFileExtensions": sorted(ALLOWED_EXTENSIONS),
        "authRequired": auth_enabled(),
        "authPublicOnly": auth_enabled(),
        "otpAuthEnabled": otp_auth_enabled(),
        "loginPhrase": WEB_LOGIN_PHRASE,
        "dingtalkOAuth": dingtalk_oauth_public_config(),
    }


@dataclass
class ActiveRun:
    run_id: str
    session_id: str
    events: queue.Queue[dict[str, Any]] = field(default_factory=queue.Queue)
    done: threading.Event = field(default_factory=threading.Event)
    final_text: str = ""
    error: str | None = None
    task_session: TaskSession = field(default_factory=TaskSession)
    cancel_notified: bool = False
    started_at: float = 0.0
    task_kind: str = ""
    last_ack_line: str = ""
    last_elapsed_line: str = ""
    last_batch_line: str = ""
    last_markdown: str = ""
    _notify_lock: threading.Lock = field(default_factory=threading.Lock)

    def emit_event(self, event: dict[str, Any]) -> None:
        etype = event.get("type")
        if etype == "ack":
            self.last_ack_line = str(event.get("line") or "")
        elif etype == "status":
            self.last_elapsed_line = str(event.get("elapsed_line") or "")
            self.last_batch_line = str(event.get("batch_line") or "")
        elif etype == "delta":
            markdown = event.get("markdown")
            if markdown:
                self.last_markdown = str(markdown)
        self.events.put(event)

    def snapshot_events(self) -> list[dict[str, Any]]:
        """重连 SSE 时回放当前进度（ack / 状态 / 已渲染正文）。"""
        events: list[dict[str, Any]] = []
        if self.last_ack_line:
            events.append({"type": "ack", "line": self.last_ack_line})
        if self.last_elapsed_line or self.last_batch_line:
            events.append(
                {
                    "type": "status",
                    "elapsed_line": self.last_elapsed_line,
                    "batch_line": self.last_batch_line,
                }
            )
        if self.last_markdown:
            events.append({"type": "delta", "markdown": self.last_markdown})
        if self.done.is_set():
            if self.error:
                events.append(
                    {
                        "type": "error",
                        "message": self.error,
                        "text": self.final_text,
                    }
                )
            else:
                events.append({"type": "done", "text": self.final_text})
        return events

    def to_active_run_dict(self) -> dict[str, Any]:
        return {
            "active": not self.done.is_set(),
            "run_id": self.run_id,
            "session_id": self.session_id,
            "ack_line": self.last_ack_line,
            "elapsed_line": self.last_elapsed_line,
            "batch_line": self.last_batch_line,
            "markdown": self.last_markdown,
        }


class RunManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, ActiveRun] = {}

    def create(self, session_id: str) -> ActiveRun:
        run_id = uuid.uuid4().hex[:12]
        run = ActiveRun(run_id=run_id, session_id=session_id)
        with self._lock:
            self._runs[run_id] = run
            self._purge_old()
        return run

    def get(self, run_id: str) -> ActiveRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def find_active_by_session(self, session_id: str) -> ActiveRun | None:
        sid = (session_id or "").strip()
        if not sid:
            return None
        with self._lock:
            for run in self._runs.values():
                if run.session_id == sid and not run.done.is_set():
                    return run
        return None

    def _purge_old(self) -> None:
        if len(self._runs) <= 50:
            return
        done_ids = [rid for rid, r in self._runs.items() if r.done.is_set()]
        for rid in done_ids[: len(done_ids) - 20]:
            self._runs.pop(rid, None)


RUN_MANAGER = RunManager()

INTERRUPT_REPLY = "⚠️ 任务已中断。"
RETRY_HINT = "💡 原消息已回填到输入框，请检查后重试。"


def _notify_run_interrupted(run: ActiveRun, text: str) -> bool:
    """立即推送 SSE 结束事件，避免前端一直等待 worker。"""
    body = (text or INTERRUPT_REPLY).strip() or INTERRUPT_REPLY
    if run.started_at > 0:
        elapsed = max(0.0, time.monotonic() - run.started_at)
        body = append_duration_footer(body, elapsed, task_kind=run.task_kind)
    with run._notify_lock:
        if run.cancel_notified:
            return False
        run.cancel_notified = True
        run.final_text = body
    run.emit_event({"type": "done", "text": body})
    return True


def _interrupt_active_run(run: ActiveRun) -> bool:
    """尽力中断 Agent run，并立即通知前端。"""
    from user_agent_pool import get_user_agent_pool

    cancel_result = run.task_session.request_cancel()
    if cancel_result is None:
        run.task_session.arm_cancel()
        cancel_result = run.task_session.request_cancel()
    try:
        get_user_agent_pool().invalidate(get_session_store().user_key(run.session_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("中断时 invalidate Agent 失败 session=%s: %s", run.session_id, exc)
    _notify_run_interrupted(run, INTERRUPT_REPLY)
    return cancel_result is not False


def _json_response(handler: SimpleHTTPRequestHandler, payload: object, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json_body(handler: SimpleHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    raw = handler.rfile.read(length) if length > 0 else b""
    if not raw:
        return {}
    data = json.loads(raw.decode("utf-8"))
    return data if isinstance(data, dict) else {}


def _task_summary(message: str) -> str:
    text = " ".join((message or "").split())
    if not text:
        return "任务"
    return text[:40] + ("…" if len(text) > 40 else "")


def _start_run_progress_watcher(
    run: ActiveRun,
    *,
    user_key: str,
    message: str,
    started_at: float,
    progress_stop: threading.Event,
) -> None:
    """每秒推送已用时与批量进度（与钉钉流式卡片三通道一致）。"""
    task_kind = classify_task_kind(message)
    estimate_s = resolve_task_estimate_seconds(task_kind, prompt=message)
    ack_line = build_task_ack_message(_task_summary(message), prompt=message)
    run.emit_event({"type": "ack", "line": ack_line})

    def loop() -> None:
        while not progress_stop.wait(PROGRESS_TICK_S):
            if run.done.is_set():
                return
            elapsed = max(0.0, time.monotonic() - started_at)
            elapsed_line = build_streaming_progress_status_line(
                elapsed,
                estimate_s=estimate_s,
            )
            batch_line = ""
            state = read_batch_progress(user_key)
            if state is not None:
                batch_line = build_batch_progress_message(state)
            run.emit_event(
                {
                    "type": "status",
                    "elapsed_line": elapsed_line,
                    "batch_line": batch_line,
                }
            )

    threading.Thread(
        target=loop,
        daemon=True,
        name=f"web-progress-{run.run_id}",
    ).start()


def _session_owner_context(user: Any) -> tuple[str, str, float]:
    if user is None:
        return "", "", 0.0
    uid = str(getattr(user, "staff_id", "") or "").strip()
    label = str(getattr(user, "display_name", "") or uid or "").strip()
    try:
        auth_created = float(getattr(user, "auth_created_at", 0) or 0)
    except (TypeError, ValueError):
        auth_created = 0.0
    return uid, label, auth_created


def _session_owner_from_user(user: Any) -> tuple[str, str]:
    uid, label, _ = _session_owner_context(user)
    return uid, label


def _attachment_message_dict(item: StoredAttachment) -> dict[str, object]:
    return item.to_message_dict()


def _format_attachment_summary(attachments: list[StoredAttachment]) -> str:
    if not attachments:
        return ""
    image_count = sum(1 for item in attachments if item.kind == "image")
    file_count = sum(1 for item in attachments if item.kind != "image")
    parts: list[str] = []
    if image_count:
        parts.append(f"{image_count} 张图片")
    if file_count:
        parts.append(f"{file_count} 个文件")
    return f"[附带 {'、'.join(parts)}]"


def _attachment_content_disposition(filename: str) -> str:
    """RFC 5987：非 ASCII 文件名用 filename*，避免 latin-1 响应头编码失败。"""
    name = (filename or "download").strip() or "download"
    ascii_name = name.encode("ascii", "ignore").decode("ascii").strip("._ ") or "download"
    if name.isascii():
        return f'attachment; filename="{ascii_name}"'
    quoted = quote(name, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted}"


def _serve_session_file(
    handler: SimpleHTTPRequestHandler,
    file_path: Path,
    *,
    download_name: str | None = None,
) -> None:
    content_type = content_type_for_path(file_path)
    data = file_path.read_bytes()
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "private, max-age=86400")
    if download_name:
        handler.send_header(
            "Content-Disposition",
            _attachment_content_disposition(download_name),
        )
    handler.end_headers()
    handler.wfile.write(data)


def _start_chat_run(
    session_id: str,
    message: str,
    *,
    attachments: list[StoredAttachment] | None = None,
    existing_run: ActiveRun | None = None,
    model: str | None = None,
    enabled_external_agents: list[str] | None = None,
) -> ActiveRun:
    store = get_session_store()
    user_key = store.user_key(session_id)
    task_kind = classify_task_kind(message)
    attachment_list = list(attachments or [])
    local_image_paths = []
    local_file_paths = []
    for item in attachment_list:
        local = local_path_from_api_path(item.api_path)
        if local is None:
            raise ValueError(f"附件不存在: {item.api_path}")
        if item.kind == "image":
            local_image_paths.append(local)
        else:
            local_file_paths.append(local)

    display_message = message
    if not display_message and attachment_list:
        display_message = _format_attachment_summary(attachment_list)

    image_urls = [item.api_path for item in attachment_list if item.kind == "image"]
    file_entries = [_attachment_message_dict(item) for item in attachment_list if item.kind != "image"]
    store.append_message(
        session_id,
        "user",
        display_message,
        images=image_urls,
        files=file_entries,
    )
    if existing_run is not None:
        run = existing_run
    else:
        run = RUN_MANAGER.create(session_id)
        run.task_session.begin(
            message or display_message,
            conversation_id=user_key,
            budget_s=float(DEFAULT_TIMEOUT_S),
        )
    clear_batch_progress(user_key)
    started_at = time.monotonic()
    run.started_at = started_at
    run.task_kind = task_kind
    agent_model = _resolve_agent_model(model)
    progress_stop = threading.Event()
    _start_run_progress_watcher(
        run,
        user_key=user_key,
        message=message,
        started_at=started_at,
        progress_stop=progress_stop,
    )

    def worker() -> None:
        last_markdown = ""
        status = "error"

        def on_render(markdown: str) -> None:
            nonlocal last_markdown
            last_markdown = markdown
            run.emit_event({"type": "delta", "markdown": markdown})

        def _append_assistant(text: str) -> None:
            output_files = consume_pending_outputs(session_id)
            store.append_message(
                session_id,
                "assistant",
                text,
                files=[item.to_message_dict() for item in output_files],
            )

        try:
            final = run_web_chat(
                session_id,
                message,
                image_paths=local_image_paths,
                file_paths=local_file_paths,
                attachment_names=[item.original_name for item in attachment_list],
                on_render=on_render,
                session_ctrl=run.task_session,
                model=agent_model,
                enabled_external_agents=enabled_external_agents,
            )
            elapsed = time.monotonic() - started_at
            body = final or last_markdown
            run.final_text = append_duration_footer(body, elapsed, task_kind=task_kind)
            _append_assistant(run.final_text)
            status = "ok"
            run.emit_event({"type": "done", "text": run.final_text})
        except TaskInterrupted:
            elapsed = time.monotonic() - started_at
            run.final_text = append_duration_footer(
                INTERRUPT_REPLY,
                elapsed,
                task_kind=task_kind,
            )
            _append_assistant(run.final_text)
            with run._notify_lock:
                if not run.cancel_notified:
                    run.cancel_notified = True
                    run.emit_event({"type": "done", "text": run.final_text})
            status = "interrupted"
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - started_at
            run.error = str(exc)
            logger.exception("Web chat run failed session=%s", session_id)
            run.final_text = append_duration_footer(
                f"⚠️ {run.error}\n\n{RETRY_HINT}",
                elapsed,
                task_kind=task_kind,
            )
            _append_assistant(run.final_text)
            run.emit_event(
                {"type": "error", "message": run.error, "text": run.final_text}
            )
        finally:
            progress_stop.set()
            clear_batch_progress(user_key)
            run.task_session.end()
            if status != "interrupted":
                get_duration_store().record(
                    task_kind,
                    time.monotonic() - started_at,
                    status=status,
                )
            run.done.set()

    threading.Thread(target=worker, daemon=True, name=f"web-chat-{run.run_id}").start()
    return run


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


class WebAgentHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEB_AGENT_DIR), **kwargs)

    def _serve_family_pk_export(self, rel_path: str) -> None:
        root = FAMILY_PK_EXPORTS_DIR.resolve()
        target = (root / rel_path).resolve()
        if not str(target).startswith(str(root)) or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type, _ = mimetypes.guess_type(str(target))
        if not content_type:
            content_type = "application/octet-stream"
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if target.suffix.lower() in {".html", ".htm"}:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: Any) -> None:
        if self.path.startswith("/api/"):
            super().log_message(fmt, *args)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if is_public_auth_path(path):
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        if not authorize_request(self, method="OPTIONS"):
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path in ("/login.html", "/login"):
            self.path = "/login.html"
            return super().do_GET()

        if path in ("/theme.js", "/dingtalk_oauth.js"):
            return super().do_GET()

        if path == "/api/auth/status":
            user = current_web_user(self)
            payload: dict[str, Any] = {
                "loggedIn": user is not None,
                "otpAuthEnabled": otp_auth_enabled(),
                "loginPhrase": WEB_LOGIN_PHRASE,
                "dingtalkOAuth": dingtalk_oauth_public_config(),
            }
            if user is not None:
                payload["user"] = {
                    "staffId": user.staff_id,
                    "displayName": user.display_name or user.staff_id,
                    "isAdmin": is_web_admin(staff_id=user.staff_id),
                }
            return _json_response(self, payload)

        if path == "/api/auth/dingtalk-config":
            return _json_response(self, dingtalk_oauth_public_config())

        if not authorize_request(self, method="GET"):
            return

        if path == "/":
            self.path = "/chat.html"
            return super().do_GET()

        if path == SHOWCASE_URL_PREFIX or path.startswith(f"{SHOWCASE_URL_PREFIX}/"):
            rel = path[len(SHOWCASE_URL_PREFIX) :].lstrip("/") or "index.html"
            return self._serve_family_pk_export(rel)

        if path == "/api/meta":
            return _json_response(self, _platform_meta())

        if path == "/api/catalog":
            try:
                return _json_response(self, _load_catalog_data())
            except (OSError, ValueError, FileNotFoundError) as exc:
                logger.exception("Failed to load catalog data")
                return _json_response(self, {"error": str(exc)}, 500)

        if path == "/api/favicon":
            qs = parse_qs(parsed.query)
            target = str((qs.get("url") or [""])[0]).strip()
            if not target:
                return _json_response(self, {"error": "missing url"}, 400)
            result = fetch_favicon(target)
            if result is None:
                self.send_error(HTTPStatus.NOT_FOUND, "favicon not found")
                return
            data, ctype = result
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/bookmarks/metadata":
            qs = parse_qs(parsed.query)
            target = str((qs.get("url") or [""])[0]).strip()
            if not target:
                return _json_response(self, {"error": "missing url"}, 400)
            meta = resolve_bookmark_metadata(target)
            return _json_response(self, meta)

        if path == "/api/message-board":
            return _handle_message_board_list(self)

        if path == "/api/sessions":
            sync_all_from_conversation_store()
            store = get_session_store()
            store.reload_from_disk()
            viewer = current_web_user(self)
            viewer_staff_id = viewer.staff_id if viewer is not None else None
            items = store.list_sessions()
            try:
                from dingtalk_user_lookup import collect_known_labels

                known = collect_known_labels(items)
            except Exception:  # noqa: BLE001
                known = {}
            sessions = [
                {
                    **s.to_dict(known_labels=known, viewer_staff_id=viewer_staff_id),
                    "running": RUN_MANAGER.find_active_by_session(s.id) is not None,
                }
                for s in items
            ]
            return _json_response(self, {"sessions": sessions})

        m = re.match(rf"^/api/sessions/({SESSION_ID_PATTERN})/active-run$", path)
        if m:
            session_id = m.group(1)
            store = get_session_store()
            if store.get_session(session_id) is None:
                return _json_response(self, {"error": "session not found"}, 404)
            run = RUN_MANAGER.find_active_by_session(session_id)
            if run is None:
                return _json_response(self, {"active": False})
            return _json_response(self, run.to_active_run_dict())

        m = re.match(rf"^/api/sessions/({SESSION_ID_PATTERN})/messages$", path)
        if m:
            session_id = m.group(1)
            store = get_session_store()
            if store.get_session(session_id) is None:
                return _json_response(self, {"error": "session not found"}, 404)
            messages = [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    **({"images": msg.images} if msg.images else {}),
                    **({"files": msg.files} if msg.files else {}),
                }
                for msg in store.get_messages(session_id)
            ]
            return _json_response(self, {"messages": messages})

        m = re.match(rf"^/api/uploads/({SESSION_ID_PATTERN})/([a-zA-Z0-9._-]+)$", path)
        if m:
            file_path = resolve_upload_file(m.group(1), m.group(2))
            if file_path is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            return _serve_session_file(self, file_path)

        m = re.match(rf"^/api/outputs/({SESSION_ID_PATTERN})/([a-zA-Z0-9._-]+)$", path)
        if m:
            file_path = resolve_output_file(m.group(1), m.group(2))
            if file_path is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            download_name = output_display_name(m.group(1), m.group(2)) or file_path.name
            return _serve_session_file(self, file_path, download_name=download_name)

        m = re.match(r"^/api/chat/stream/([a-f0-9]+)$", path)
        if m:
            return self._handle_sse(m.group(1))

        return super().do_GET()

    def _write_sse_event(self, event: dict[str, Any]) -> None:
        payload = json.dumps(event, ensure_ascii=False)
        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _handle_sse(self, run_id: str) -> None:
        run = RUN_MANAGER.get(run_id)
        if run is None:
            self.send_error(HTTPStatus.NOT_FOUND, "run not found")
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        deadline = time.monotonic() + RUN_TTL_S
        sent_done = False
        try:
            for event in run.snapshot_events():
                self._write_sse_event(event)
                if event.get("type") in ("done", "error"):
                    sent_done = True
                    return

            while time.monotonic() < deadline:
                try:
                    event = run.events.get(timeout=SSE_POLL_S)
                except queue.Empty:
                    if run.done.is_set():
                        break
                    continue
                self._write_sse_event(event)
                if event.get("type") in ("done", "error"):
                    sent_done = True
                    break
            if not sent_done and run.done.is_set():
                if run.error:
                    payload = {"type": "error", "message": run.error, "text": run.final_text}
                else:
                    payload = {"type": "done", "text": run.final_text}
                self._write_sse_event(payload)
        except (BrokenPipeError, ConnectionResetError):
            # 刷新页面 / 切 tab 会断开 SSE；后台任务继续，客户端可重连
            logger.info(
                "SSE client disconnected run=%s session=%s (task continues)",
                run_id,
                run.session_id,
            )

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/auth/login":
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            code = str(body.get("code") or "").strip()
            token, user, err = get_web_otp_store().verify_otp_and_create_session(code)
            if not token or user is None:
                return _json_response(self, {"error": err or "登录失败"}, 401)
            payload = {
                "ok": True,
                "user": {
                    "staffId": user.staff_id,
                    "displayName": user.display_name or user.staff_id,
                },
            }
            body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            set_session_cookie(self, token)
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)
            return

        if path == "/api/auth/dingtalk-oauth":
            if not dingtalk_oauth_enabled():
                return _json_response(self, {"error": "钉钉 OAuth 免登未启用"}, 503)
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            auth_code = str(body.get("authCode") or body.get("code") or "").strip()
            try:
                token, user, err = login_with_auth_code(auth_code)
            except Exception as exc:  # noqa: BLE001
                logger.exception("钉钉 OAuth 登录异常")
                return _json_response(self, {"error": f"钉钉登录异常：{exc}"}, 500)
            if not token or user is None:
                return _json_response(self, {"error": err or "钉钉登录失败"}, 401)
            payload = {
                "ok": True,
                "user": {
                    "staffId": user.staff_id,
                    "displayName": user.display_name or user.staff_id,
                },
            }
            body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            set_session_cookie(self, token)
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)
            return

        if path == "/api/auth/logout":
            logout_current_session(self)
            return _json_response(self, {"ok": True})

        if not authorize_request(self, method="POST"):
            return

        if path == "/api/sessions":
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            title = str(body.get("title") or "新对话")
            owner_id, owner_label = _session_owner_from_user(current_web_user(self))
            meta = get_session_store().create_session(
                title=title,
                owner_id=owner_id,
                owner_label=owner_label,
            )
            return _json_response(
                self,
                meta.to_dict(viewer_staff_id=owner_id or None),
                201,
            )

        if path == "/api/chat":
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            session_id = str(body.get("session_id") or "").strip()
            message = str(body.get("message") or "").strip()
            agent_model = _resolve_agent_model(body.get("model"))
            enabled_external_agents = resolve_enabled_external_agent_ids(
                body.get("enabled_external_agents"),
            )
            raw_attachments = body.get("attachments")
            if not isinstance(raw_attachments, list):
                raw_attachments = []
            legacy_images = body.get("images")
            if isinstance(legacy_images, list):
                for item in legacy_images:
                    if isinstance(item, dict):
                        raw_attachments.append(item)
            attachment_items: list[dict[str, str]] = []
            for item in raw_attachments:
                if isinstance(item, dict):
                    attachment_items.append(item)
            if not session_id or (not message and not attachment_items):
                return _json_response(
                    self,
                    {"error": "session_id required; message or attachments required"},
                    400,
                )
            store = get_session_store()
            if store.get_session(session_id) is None:
                return _json_response(self, {"error": "session not found"}, 404)
            viewer = current_web_user(self)
            viewer_staff_id = viewer.staff_id if viewer is not None else None
            if store.is_read_only_for_viewer(session_id, viewer_staff_id):
                meta = store.get_session(session_id)
                if meta is not None and meta.source == "dingtalk":
                    err = "钉钉同步会话只读，请在 Web 新建对话继续"
                else:
                    err = "该会话归属他人，仅供查看；请新建对话继续"
                return _json_response(self, {"error": err}, 403)
            owner_id, owner_label = _session_owner_from_user(viewer)
            store.ensure_web_owner(
                session_id,
                owner_id=owner_id,
                owner_label=owner_label,
            )
            user_key = store.user_key(session_id)
            display_message = message
            if not display_message and attachment_items:
                display_message = "[附带附件]"
            run = RUN_MANAGER.create(session_id)
            run.task_session.begin(
                message or display_message,
                conversation_id=user_key,
                budget_s=float(DEFAULT_TIMEOUT_S),
            )
            try:
                saved_attachments = save_chat_attachments(session_id, attachment_items)
            except FileUploadError as exc:
                run.task_session.end()
                run.done.set()
                return _json_response(self, {"error": str(exc)}, 400)
            try:
                _start_chat_run(
                    session_id,
                    message,
                    attachments=saved_attachments,
                    existing_run=run,
                    model=agent_model,
                    enabled_external_agents=enabled_external_agents,
                )
            except Exception as exc:  # noqa: BLE001
                run.task_session.end()
                run.done.set()
                logger.exception("启动 Web chat 失败 session=%s", session_id)
                return _json_response(self, {"error": str(exc)}, 500)
            return _json_response(self, {"run_id": run.run_id, "session_id": session_id})

        if path == "/api/bookmarks":
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            return _handle_bookmarks_save(self, body)

        if path == "/api/bookmarks/import-legacy":
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            return _handle_bookmarks_import_legacy(self, body)

        if path == "/api/message-board":
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            return _handle_message_board_create(self, body)

        if path == "/api/chat/cancel":
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            run_id = str(body.get("run_id") or "").strip()
            session_id = str(body.get("session_id") or "").strip()
            run = RUN_MANAGER.get(run_id) if run_id else None
            if run is None and session_id:
                run = RUN_MANAGER.find_active_by_session(session_id)
            if run is None:
                return _json_response(self, {"error": "run not found"}, 404)
            if not _interrupt_active_run(run):
                return _json_response(self, {"error": "当前任务无法中断"}, 409)
            return _json_response(self, {"ok": True})

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_PUT(self) -> None:
        if not authorize_request(self, method="PUT"):
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path != "/api/bookmarks":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            body = _read_json_body(self)
        except json.JSONDecodeError:
            return _json_response(self, {"error": "invalid json"}, 400)
        return _handle_bookmarks_save(self, body)

    def do_DELETE(self) -> None:
        if not authorize_request(self, method="DELETE"):
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        m_board = re.match(r"^/api/message-board/([a-f0-9]{32})$", path)
        if m_board:
            return _handle_message_board_delete(self, m_board.group(1))

        m = re.match(rf"^/api/sessions/({SESSION_ID_PATTERN})$", path)
        if not m:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        user = current_web_user(self)
        if user is not None and not is_web_admin(staff_id=user.staff_id):
            return _json_response(self, {"error": web_admin_denial_message()}, 403)
        ok = get_session_store().delete_session(m.group(1))
        if not ok:
            return _json_response(self, {"error": "session not found"}, 404)
        return _json_response(self, {"ok": True})


def serve(host: str, port: int) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = ThreadingHTTPServer((host, port), WebAgentHandler)
    print(f"Web Agent: http://{host}:{port}/")

    def _shutdown(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _shutdown)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def ensure_server(
    host: str | None = None,
    port: int | None = None,
    wait_s: float = 3.0,
    *,
    watch: bool = True,
) -> tuple[str, int]:
    from server_watch import (  # noqa: E402
        is_watch_running,
        kill_all_watch_processes,
        kill_process_on_port,
        start_watch_background,
    )

    cfg = _load_config()
    use_host = host or str(cfg.get("host") or DEFAULT_HOST)
    use_port = port if port is not None else int(cfg.get("port") or DEFAULT_PORT)
    check_host = "127.0.0.1" if use_host == "0.0.0.0" else use_host

    if watch and is_watch_running() and is_port_open(check_host, use_port):
        return use_host, use_port

    if not watch and is_port_open(check_host, use_port):
        return use_host, use_port

    if watch:
        kill_all_watch_processes()
        kill_process_on_port(use_port)
    elif is_port_open(check_host, use_port):
        return use_host, use_port

    if watch:
        proc = start_watch_background(host=use_host, port=use_port)
        deadline = time.monotonic() + max(wait_s, 15.0)
    else:
        log_path = WEB_AGENT_DIR / "data" / "server.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fp = open(log_path, "a", encoding="utf-8")
        proc = subprocess.Popen(
            [
                _resolve_python_executable(),
                str(Path(__file__).resolve()),
                "--serve",
                "--host",
                use_host,
                "--port",
                str(use_port),
            ],
            cwd=str(REPO_ROOT),
            stdout=log_fp,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline = time.monotonic() + wait_s

    while time.monotonic() < deadline:
        if is_port_open(check_host, use_port):
            return use_host, use_port
        if proc.poll() is not None:
            raise RuntimeError("Web Agent 服务启动失败")
        time.sleep(0.1)
    raise RuntimeError("Web Agent 服务启动超时")


def main() -> int:
    parser = argparse.ArgumentParser(description="Yaahlan Web Agent HTTP 服务")
    parser.add_argument("--ensure", action="store_true", help="若未运行则后台启动（默认带源码监视）")
    parser.add_argument("--serve", action="store_true", help="前台运行 HTTP 服务")
    parser.add_argument("--no-watch", action="store_true", help="禁用源码变更自动重启")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    cfg = _load_config()
    host = args.host or str(cfg.get("host") or DEFAULT_HOST)
    port = args.port if args.port is not None else int(cfg.get("port") or DEFAULT_PORT)

    watch = not args.no_watch

    if args.ensure:
        ensure_server(host, port, watch=watch)
        display = "127.0.0.1" if host == "0.0.0.0" else host
        print(f"http://{display}:{port}/")
        return 0

    if args.serve:
        if watch:
            from server_watch import run_watch  # noqa: E402

            run_watch(host=host, port=port)
        else:
            serve(host, port)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
