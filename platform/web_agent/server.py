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
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))

from project.loader import (  # noqa: E402
    get_project_id,
    load_sources,
    web_agent_subtitle,
    web_agent_title,
)
from project.runtime_env import ensure_project_env  # noqa: E402

ensure_project_env()

from cursor_runner import DEFAULT_MODEL, resolve_agent_timeout_s  # noqa: E402
from external_agent_config import (  # noqa: E402
    external_agents_from_config,
    resolve_enabled_external_agent_ids,
)
from batch_progress import (  # noqa: E402
    build_batch_progress_message,
    clear_batch_progress,
    read_batch_progress,
)
from batch_result import clear_batch_result  # noqa: E402
from service_agent_run_log import clear_service_agent_run_log  # noqa: E402
from external_agent_progress import (  # noqa: E402
    build_external_agent_progress_message,
    clear_external_agent_progress,
    read_external_agent_progress,
)
from duration_history import classify_task_kind  # noqa: E402
from progress_message import (  # noqa: E402
    build_streaming_progress_status_line,
    build_task_ack_message,
    resolve_task_estimate_seconds,
)
from web_session_context import should_rotate_cursor_agent  # noqa: E402
from task_session import TaskSession  # noqa: E402
from dingtalk_web_sync import sync_all_from_conversation_store  # noqa: E402
from web_file_store import (  # noqa: E402
    ALLOWED_EXTENSIONS,
    FileUploadError,
    MAX_ATTACHMENTS_PER_MESSAGE,
    MAX_FILE_BYTES,
    MAX_IMAGE_BYTES,
    StoredAttachment,
    content_type_for_path,
    local_path_from_api_path,
    output_display_name,
    resolve_output_file,
    resolve_upload_file,
    save_chat_attachments,
)
from analytics_store import get_analytics_store  # noqa: E402
from cursor_usage import (  # noqa: E402
    CursorAuthError,
    clear_user_today_live_cache,
    clear_user_usage_daily_cache,
    get_usage_date_bounds,
    parse_cursor_session_input,
    should_clear_usage_cache_on_credential_update,
    summarize_user_usage as summarize_cursor_user_usage,
    verify_session_token,
)
from cursor_usage_store import get_cursor_usage_store  # noqa: E402
from web_session_store import filter_sessions_by_search, filter_sessions_by_scope, get_session_store, sort_sessions_for_display, compute_sessions_list_etag, compute_messages_page_etag, estimate_messages_page_meta, resolve_user_message_author  # noqa: E402
from web_run_store import (  # noqa: E402
    RUN_STATUS_DONE,
    RUN_STATUS_ERROR,
    RUN_STATUS_INTERRUPTED,
    RUN_STATUS_RUNNING,
    RunMeta,
    compute_active_run_etag,
    get_run_store,
)
from web_prompt import normalize_reply_mode, finalize_web_reply_text  # noqa: E402
from run_progress_reply import (  # noqa: E402
    INTERRUPT_HEADLINE,
    RETRY_HINT,
    SERVICE_RESTART_HEADLINE,
    build_run_stop_reply,
)
from web_admin_grants import is_super_admin  # noqa: E402
from web_admin_permission import is_web_admin, web_admin_denial_message  # noqa: E402
from web_admin_apply import application_status_for_staff, submit_application  # noqa: E402
from web_admin_manage import (  # noqa: E402
    enrich_selectable_users_with_admin_roles,
    list_admin_users,
    quit_admin_role,
    remove_admin_list_user,
    set_admin_permissions,
    set_admin_role,
)
from web_auth import authorize_request, auth_enabled, logout_current_session, _effective_client_ip  # noqa: E402
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
from service_agent_webhook import SIGNATURE_HEADER, handle_webhook_body  # noqa: E402
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
from dingtalk_user_lookup import (  # noqa: E402
    lookup_auth_user_display_name,
    lookup_staff_public_name,
)

logger = logging.getLogger("web-agent")

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 18766
CONFIG_PATH = WEB_AGENT_DIR / "config.json"
FAMILY_PK_EXPORTS_DIR = REPO_ROOT / "platform" / "family_pk_report" / "exports"
PLATFORM_GUIDE_DIR = REPO_ROOT / "platform" / "exports" / "cursor-platform-guide"
SHOWCASE_URL_PREFIX = "/family-pk-showcase"
PLATFORM_GUIDE_URL_PREFIX = "/platform-guide"
KEYNOTE_URL_PREFIX = "/keynote"
KEYNOTE_DIR = WEB_AGENT_DIR / "keynote"
KEYNOTE_PREVIEW_HTML = KEYNOTE_DIR / "preview.html"
SSE_POLL_S = 0.25
RUN_TTL_S = 3600
RUN_RECOVERY_GRACE_S = 120.0
PROGRESS_TICK_S = 1.0
SESSION_ID_PATTERN = r"[a-z0-9]+"
ANALYTICS_SCRIPT_TAG = '<script src="/analytics.js"></script>'

_CONVERSATIONS_SYNC_INTERVAL_S = 30.0
_last_conversations_sync_at = 0.0


def _maybe_sync_conversations(parsed_url) -> None:
    """钉钉 conversations 增量同步：轮询时节流，避免每次 list_sessions 都读盘。"""
    global _last_conversations_sync_at
    qs = parse_qs(parsed_url.query)
    force = (qs.get("sync") or ["0"])[0].strip().lower() in ("1", "true", "yes")
    now = time.monotonic()
    if not force and now - _last_conversations_sync_at < _CONVERSATIONS_SYNC_INTERVAL_S:
        return
    sync_all_from_conversation_store()
    _last_conversations_sync_at = now


def _inject_analytics_script(html: str) -> str:
    if "/analytics.js" in html or "WebAgentAnalytics" in html:
        return html
    if "</body>" in html:
        return html.replace("</body>", f"{ANALYTICS_SCRIPT_TAG}\n</body>", 1)
    return html + ANALYTICS_SCRIPT_TAG


def _record_analytics(
    handler: SimpleHTTPRequestHandler,
    *,
    event: str,
    page: str = "",
    props: dict[str, Any] | None = None,
    source: str = "server",
) -> None:
    user = current_web_user(handler)
    get_analytics_store().record_event(
        event=event,
        page=page or urlparse(handler.path).path,
        staff_id=user.staff_id if user is not None else "",
        display_name=user.display_name if user is not None else "",
        source=source,
        props=props,
        ip=_effective_client_ip(handler),
    )


def _handle_analytics_event_post(handler: SimpleHTTPRequestHandler) -> None:
    try:
        body = _read_json_body(handler)
    except json.JSONDecodeError:
        return _json_response(handler, {"error": "invalid json"}, 400)
    event = str(body.get("event") or "").strip()
    if not event:
        return _json_response(handler, {"error": "missing event"}, 400)
    page = str(body.get("page") or urlparse(handler.path).path).strip()
    props = body.get("props") if isinstance(body.get("props"), dict) else {}
    user = current_web_user(handler)
    ok = get_analytics_store().record_event(
        event=event,
        page=page,
        staff_id=user.staff_id if user is not None else "",
        display_name=user.display_name if user is not None else "",
        source="client",
        props=props,
        ip=_effective_client_ip(handler),
    )
    return _json_response(handler, {"ok": ok})


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


_CATALOG_CACHE: dict[str, Any] | None = None
_CATALOG_CACHE_FINGERPRINT = ""


def _catalog_sources_fingerprint() -> str:
    from project.catalog_paths import module_registry_path  # noqa: WPS433
    from project.loader import load_sources, sources_path  # noqa: WPS433

    parts: list[str] = []
    src = sources_path()
    if src.is_file():
        parts.append(f"{src}:{src.stat().st_mtime_ns}")
    try:
        sources = load_sources()
    except (OSError, ValueError):
        return ""
    modules_cfg = sources.get("modules")
    if not isinstance(modules_cfg, list):
        return "\n".join(parts)
    for mod in modules_cfg:
        if not isinstance(mod, dict):
            continue
        mod_id = str(mod.get("id", "")).strip()
        registry_rel = str(mod.get("registry", "")).strip()
        if not mod_id or not registry_rel:
            continue
        registry_path = module_registry_path(mod_id, registry_rel)
        if registry_path.is_file():
            parts.append(f"{registry_path}:{registry_path.stat().st_mtime_ns}")
    return "\n".join(parts)


def _load_catalog_data_cached() -> dict[str, Any]:
    global _CATALOG_CACHE, _CATALOG_CACHE_FINGERPRINT
    fingerprint = _catalog_sources_fingerprint()
    if _CATALOG_CACHE is not None and fingerprint and fingerprint == _CATALOG_CACHE_FINGERPRINT:
        return _CATALOG_CACHE
    data = _load_catalog_data()
    if fingerprint:
        _CATALOG_CACHE = data
        _CATALOG_CACHE_FINGERPRINT = fingerprint
    return data


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


WEB_DOCS_PATH = WEB_AGENT_DIR / "config" / "web_docs.json"


def _load_web_docs() -> dict[str, Any]:
    if not WEB_DOCS_PATH.is_file():
        return {"title": "关于 Yaahlan Web Agent", "intro": "", "categories": []}
    try:
        data = json.loads(WEB_DOCS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("读取 web_docs.json 失败: %s", exc)
        return {"title": "关于 Yaahlan Web Agent", "intro": "", "categories": []}
    if not isinstance(data, dict):
        return {"title": "关于 Yaahlan Web Agent", "intro": "", "categories": []}
    return data


KEYNOTE_SCENES_JSON = KEYNOTE_DIR / "scenes.json"


def _load_feature_demos(cfg: dict[str, Any]) -> list[dict[str, str]]:
    override = cfg.get("featureDemos")
    if isinstance(override, list) and override:
        out: list[dict[str, str]] = []
        for item in override:
            if not isinstance(item, dict) or not item.get("demo"):
                continue
            if item.get("emptyCarousel") is False:
                continue
            out.append(
                {
                    "label": str(item.get("label") or ""),
                    "title": str(item.get("title") or ""),
                    "desc": str(item.get("desc") or ""),
                    "demo": str(item.get("demo") or ""),
                    "layout": str(item.get("layout") or ""),
                }
            )
        return out
    try:
        scenes = json.loads(KEYNOTE_SCENES_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("读取 scenes.json 失败: %s", exc)
        return []
    if not isinstance(scenes, list):
        return []
    # 空态轮播使用 scenes.json 中全部可展示 feature demo（随机切换）；
    # featureDemoPreviewIds 仅用于 Keynote 内 mock 小窗轮播，不限制此处。
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        if scene.get("type") != "feature" or not scene.get("demo") or scene.get("textOnly"):
            continue
        if scene.get("emptyCarousel") is False:
            continue
        demo_id = str(scene.get("demo") or "")
        if demo_id in seen:
            continue
        seen.add(demo_id)
        out.append(
            {
                "label": str(scene.get("label") or ""),
                "title": str(scene.get("title") or ""),
                "desc": str(scene.get("desc") or ""),
                "demo": demo_id,
                "layout": str(scene.get("layout") or ""),
            }
        )
    return out


def _platform_meta() -> dict[str, int | str]:
    cfg = _load_config()
    title = str(cfg.get("title") or web_agent_title())
    subtitle = str(cfg.get("subtitle") or web_agent_subtitle())

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
    try:
        data = load_sources()
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
    except (OSError, json.JSONDecodeError, FileNotFoundError, ValueError):
        pass

    return {
        "title": title,
        "subtitle": subtitle,
        "projectId": get_project_id(),
        "mcp_count": mcp_count,
        "skills_count": skills_count,
        "modules_count": modules_count,
        "capabilities_count": capabilities_count,
        "defaultAgentModel": _default_agent_model(cfg),
        "agentModels": _agent_models_from_config(cfg),
        "externalAgents": _external_agents_meta(cfg),
        "quickPrompts": cfg.get("quickPrompts") or [],
        "quickPromptCount": int(cfg.get("quickPromptCount") or 4),
        "emptyIntro": cfg.get("emptyIntro") or {},
        "featureDemos": _load_feature_demos(cfg),
        "featureDemoRotateMs": int(cfg.get("featureDemoRotateMs") or 10000),
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
    last_external_line: str = ""
    last_phase_line: str = ""
    last_markdown: str = ""
    last_process: dict[str, Any] | None = None
    reply_mode: str = "standard"
    tailers_attached: bool = False
    _notify_lock: threading.Lock = field(default_factory=threading.Lock)

    def emit_event(self, event: dict[str, Any]) -> None:
        etype = event.get("type")
        if etype == "ack":
            self.last_ack_line = str(event.get("line") or "")
        elif etype == "status":
            if "elapsed_line" in event:
                self.last_elapsed_line = str(event.get("elapsed_line") or "")
            if "batch_line" in event:
                self.last_batch_line = str(event.get("batch_line") or "")
            if "external_line" in event:
                self.last_external_line = str(event.get("external_line") or "")
            if "phase_line" in event:
                self.last_phase_line = str(event.get("phase_line") or "")
        elif etype == "delta":
            markdown = event.get("markdown")
            if markdown:
                self.last_markdown = str(markdown)
            proc = event.get("process")
            if isinstance(proc, dict):
                from web_run_store import _merge_process_payload, _process_has_stream_content

                prev = self.last_process if isinstance(self.last_process, dict) else None
                self.last_process = _merge_process_payload(prev, proc)
                from web_run_store import resolve_process_phase_line

                self.last_phase_line = resolve_process_phase_line(self.last_process)
        self.events.put(event)

    def snapshot_events(self) -> list[dict[str, Any]]:
        """重连 SSE 时回放当前进度（ack / 状态 / 已渲染正文）。"""
        events: list[dict[str, Any]] = []
        if self.last_ack_line:
            events.append({"type": "ack", "line": self.last_ack_line})
        elapsed_line = self.last_elapsed_line
        if not self.done.is_set() and self.started_at > 0:
            elapsed_line = _build_live_elapsed_line(self)
        if elapsed_line or self.last_batch_line or self.last_external_line or self.last_phase_line:
            events.append(
                {
                    "type": "status",
                    "elapsed_line": elapsed_line,
                    "batch_line": self.last_batch_line,
                    "external_line": self.last_external_line,
                    "phase_line": self.last_phase_line,
                }
            )
        if self.last_markdown or self.last_process:
            evt: dict[str, Any] = {"type": "delta", "markdown": self.last_markdown}
            if isinstance(self.last_process, dict):
                evt["process"] = self.last_process
            events.append(evt)
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
        elapsed_line = self.last_elapsed_line
        if not self.done.is_set() and self.started_at > 0:
            elapsed_line = _build_live_elapsed_line(self)
        return {
            "active": not self.done.is_set(),
            "run_id": self.run_id,
            "session_id": self.session_id,
            "ack_line": self.last_ack_line,
            "elapsed_line": elapsed_line,
            "batch_line": self.last_batch_line,
            "external_line": self.last_external_line,
            "phase_line": self.last_phase_line,
            "markdown": self.last_markdown,
            "process": self.last_process,
        }


class RunManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, ActiveRun] = {}
        self._session_active: dict[str, str] = {}

    def register(self, run: ActiveRun) -> ActiveRun:
        with self._lock:
            self._runs[run.run_id] = run
            if not run.done.is_set():
                sid = (run.session_id or "").strip()
                if sid:
                    self._session_active[sid] = run.run_id
            self._purge_old()
        if not run.done.is_set():
            _invalidate_active_run_ids_cache()
        return run

    def create(self, session_id: str, *, run_id: str | None = None) -> ActiveRun:
        rid = run_id or uuid.uuid4().hex[:12]
        run = ActiveRun(run_id=rid, session_id=session_id)
        return self.register(run)

    def get(self, run_id: str) -> ActiveRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def find_active_by_session(self, session_id: str) -> ActiveRun | None:
        sid = (session_id or "").strip()
        if not sid:
            return None
        with self._lock:
            rid = self._session_active.get(sid)
            if rid:
                run = self._runs.get(rid)
                if run is not None and not run.done.is_set():
                    return run
                self._session_active.pop(sid, None)
            for run in self._runs.values():
                if run.session_id == sid and not run.done.is_set():
                    self._session_active[sid] = run.run_id
                    return run
        return None

    def release_session(self, run: ActiveRun) -> None:
        sid = (run.session_id or "").strip()
        if not sid:
            return
        with self._lock:
            if self._session_active.get(sid) == run.run_id:
                self._session_active.pop(sid, None)
        _invalidate_active_run_ids_cache()

    def active_session_ids(self) -> set[str]:
        with self._lock:
            return {
                (run.session_id or "").strip()
                for run in self._runs.values()
                if not run.done.is_set() and (run.session_id or "").strip()
            }

    def _purge_old(self) -> None:
        if len(self._runs) <= 50:
            return
        done_ids = [rid for rid, r in self._runs.items() if r.done.is_set()]
        for rid in done_ids[: len(done_ids) - 20]:
            self._runs.pop(rid, None)


RUN_MANAGER = RunManager()

INTERRUPT_REPLY = INTERRUPT_HEADLINE


def _notify_run_interrupted(run: ActiveRun, text: str) -> bool:
    """立即推送 SSE 结束事件，避免前端一直等待 worker。"""
    body = (text or INTERRUPT_REPLY).strip() or INTERRUPT_REPLY
    if run.started_at > 0:
        elapsed = max(0.0, time.monotonic() - run.started_at)
        user_key = get_session_store().user_key(run.session_id)
        body = finalize_web_reply_text(
            body,
            elapsed,
            task_kind=run.task_kind,
            reply_mode=run.reply_mode,
            user_key=user_key,
        )
    with run._notify_lock:
        if run.cancel_notified:
            return False
        run.cancel_notified = True
        run.final_text = body
    run.emit_event({"type": "done", "text": body})
    run.done.set()
    RUN_MANAGER.release_session(run)
    return True


def _interrupt_active_run(run: ActiveRun) -> bool:
    """尽力中断 Agent run，并立即通知前端。"""
    from run_child_processes import kill_run_child_processes
    from user_agent_pool import get_user_agent_pool
    from web_run_executor import _terminate_worker_process, is_shared_worker_daemon_pid

    store = get_run_store()
    store.request_cancel(run.run_id)
    store.mark_status(run.run_id, RUN_STATUS_INTERRUPTED)

    user_key = get_session_store().user_key(run.session_id)
    interrupt_body = build_run_stop_reply(
        INTERRUPT_REPLY,
        user_key=user_key,
        stream_markdown=run.last_markdown,
        batch_line=run.last_batch_line,
        external_line=run.last_external_line,
    )
    _notify_run_interrupted(run, interrupt_body)
    if run.final_text:
        get_session_store().append_message(run.session_id, "assistant", run.final_text)

    if user_key:
        kill_run_child_processes(user_key)
    meta = store.get_run(run.run_id)
    if meta is not None and meta.worker_pid > 0:
        worker_pid = int(meta.worker_pid)
        if not is_shared_worker_daemon_pid(worker_pid):
            _terminate_worker_process(worker_pid)

    # 勿对 HTTP 进程内 ActiveRun.task_session 调用 request_cancel()：
    # worker 在独立子进程/线程内使用 FileBackedTaskSession + 落盘 cancel 标记；
    # request_cancel 会 _terminate_child_processes() 杀掉本进程全部子 worker，误伤其它会话。
    try:
        if user_key:
            get_user_agent_pool().invalidate(user_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("中断时 invalidate Agent 失败 session=%s: %s", run.session_id, exc)
    return True


def _monotonic_started_at_from_meta(meta: RunMeta) -> float:
    """将落盘 wall-clock 起点映射为 monotonic 基准，避免恢复后计时从 0 重计。"""
    started = float(meta.started_at or 0.0)
    if started <= 0:
        return time.monotonic()
    elapsed = max(0.0, time.time() - started)
    return time.monotonic() - elapsed


def _build_web_elapsed_status_line(elapsed_s: float) -> str:
    """Web 已用时行仅展示 elapsed；总预估固定在 ack 行，避免 SSE/轮询估算不一致导致「预计还需」闪烁。"""
    return build_streaming_progress_status_line(elapsed_s, estimate_s=None)


def _build_live_elapsed_line(run: ActiveRun) -> str:
    elapsed = max(0.0, time.monotonic() - run.started_at)
    return _build_web_elapsed_status_line(elapsed)


def _apply_snapshot_to_run(run: ActiveRun, snap) -> None:
    run.last_ack_line = snap.last_ack_line
    run.last_elapsed_line = snap.last_elapsed_line
    run.last_batch_line = snap.last_batch_line
    run.last_external_line = snap.last_external_line
    run.last_phase_line = snap.last_phase_line
    run.last_markdown = snap.last_markdown
    if isinstance(getattr(snap, "last_process", None), dict):
        run.last_process = snap.last_process
    run.final_text = snap.final_text
    run.error = snap.error


def _active_run_from_store_meta(meta: RunMeta) -> ActiveRun:
    existing = RUN_MANAGER.get(meta.run_id)
    if existing is not None:
        return existing
    store = get_run_store()
    snap = store.get_snapshot(meta.run_id)
    run = RUN_MANAGER.create(meta.session_id, run_id=meta.run_id)
    run.task_kind = classify_task_kind(meta.message)
    run.reply_mode = normalize_reply_mode(meta.reply_mode)
    run.started_at = _monotonic_started_at_from_meta(meta)
    _apply_snapshot_to_run(run, snap)
    if meta.status != RUN_STATUS_RUNNING:
        run.done.set()
        RUN_MANAGER.release_session(run)
    return run


def _attach_run_tailers(run: ActiveRun, meta: RunMeta) -> None:
    if run.tailers_attached:
        return
    run.tailers_attached = True
    progress_stop = threading.Event()
    _start_run_event_tailer(run, progress_stop=progress_stop)
    _start_run_progress_watcher(
        run,
        user_key=get_session_store().user_key(meta.session_id),
        message=meta.message,
        started_at=run.started_at,
        progress_stop=progress_stop,
        session_id=meta.session_id,
    )


def _within_run_recovery_grace(meta: RunMeta) -> bool:
    return (time.time() - float(meta.started_at)) < RUN_RECOVERY_GRACE_S


def _try_respawn_recent_run(meta: RunMeta) -> ActiveRun | None:
    """服务重启后 worker 已退出时，对近期任务尝试重新派发 worker。"""
    if meta.status != RUN_STATUS_RUNNING or not _within_run_recovery_grace(meta):
        return None
    _start_run_worker(meta.run_id)
    store = get_run_store()
    if not store.is_worker_alive(meta.run_id):
        return None
    run = _active_run_from_store_meta(meta)
    _attach_run_tailers(run, meta)
    refreshed = store.get_run(meta.run_id)
    logger.info(
        "重启后恢复任务 run=%s session=%s worker_pid=%s",
        meta.run_id,
        meta.session_id,
        int(refreshed.worker_pid) if refreshed else 0,
    )
    return run


def _recover_running_meta(meta: RunMeta, *, allow_fresh_spawn: bool = False) -> ActiveRun:
    """恢复 RUNNING 任务：挂 SSE；近期任务可在 worker 丢失后重新派发。"""
    store = get_run_store()
    if meta.status != RUN_STATUS_RUNNING:
        return _active_run_from_store_meta(meta)

    existing = RUN_MANAGER.get(meta.run_id)
    if existing is not None:
        if store.is_worker_alive(meta.run_id) and not existing.tailers_attached:
            _attach_run_tailers(existing, meta)
        return existing

    if store.is_worker_alive(meta.run_id):
        run = _active_run_from_store_meta(meta)
        _attach_run_tailers(run, meta)
        return run

    if allow_fresh_spawn or _within_run_recovery_grace(meta):
        respawned = _try_respawn_recent_run(meta)
        if respawned is not None:
            return respawned
        if store.is_worker_alive(meta.run_id):
            run = _active_run_from_store_meta(meta)
            _attach_run_tailers(run, meta)
            return run

    if meta.worker_pid > 0 or store.has_run_activity(meta.run_id):
        _finalize_orphan_run(meta)
        return _active_run_from_store_meta(meta)

    if allow_fresh_spawn:
        _finalize_orphan_run(meta)
    return _active_run_from_store_meta(meta)


def _get_or_recover_run(run_id: str) -> ActiveRun | None:
    run = RUN_MANAGER.get(run_id)
    if run is not None:
        return run
    store = get_run_store()
    meta = store.get_run(run_id)
    if meta is None:
        return None
    return _recover_running_meta(meta, allow_fresh_spawn=True)


def _run_cancelled_or_interrupted(meta: RunMeta) -> bool:
    if meta.status == RUN_STATUS_INTERRUPTED:
        return True
    return bool(meta.cancel_requested)


def _assistant_reply_since_last_user(session_id: str) -> bool:
    session_store = get_session_store()
    messages, _ = session_store.get_messages(session_id, tail=24)
    for msg in reversed(messages):
        if msg.role == "assistant":
            return True
        if msg.role == "user":
            break
    return False


def _run_has_persisted_reply(meta: RunMeta) -> bool:
    """该 run 对应用户提问是否已有落盘 assistant 回复。"""
    prompt = (meta.display_message or meta.message or "").strip()
    if not prompt:
        return False
    session_store = get_session_store()
    messages, _ = session_store.get_messages(meta.session_id, tail=48)
    seen_user = False
    for msg in messages:
        if msg.role == "user":
            user_text = (msg.content or "").strip()
            if user_text == prompt:
                seen_user = True
            elif seen_user:
                return False
            continue
        if seen_user and msg.role == "assistant":
            return True
    return False


def _release_memory_run(run_id: str) -> None:
    mem_run = RUN_MANAGER.get(run_id)
    if mem_run is None or mem_run.done.is_set():
        return
    mem_run.done.set()
    RUN_MANAGER.release_session(mem_run)


def _supersede_prior_session_runs(session_id: str, *, keep_run_id: str) -> None:
    """新消息开始时结束同会话残留 running run，避免后续任务完成后又被当成 active。"""
    from web_run_executor import _terminate_worker_process

    store = get_run_store()
    for meta in list(store.list_active_runs()):
        if meta.session_id != session_id or meta.run_id == keep_run_id:
            continue
        if meta.status != RUN_STATUS_RUNNING:
            continue
        fresh = store.get_run(meta.run_id) or meta
        snap = store.get_snapshot(fresh.run_id)
        if _run_has_persisted_reply(fresh):
            store.mark_status(fresh.run_id, RUN_STATUS_DONE)
            _release_memory_run(fresh.run_id)
            continue
        if snap.final_text and not str(snap.final_text).lstrip().startswith("⚠️"):
            store.mark_status(fresh.run_id, RUN_STATUS_DONE)
            _release_memory_run(fresh.run_id)
            continue
        if store.is_worker_alive(fresh.run_id):
            store.update_meta(fresh.run_id, cancel_requested=True)
            worker_pid = int(fresh.worker_pid or 0)
            if worker_pid > 0:
                _terminate_worker_process(worker_pid)
        _finalize_orphan_run(store.get_run(fresh.run_id) or fresh)
        _release_memory_run(fresh.run_id)


def _finalize_cancelled_run(meta: RunMeta) -> None:
    """用户中断后 worker 已退出时的兜底落盘（避免误报服务重启）。"""
    store = get_run_store()
    fresh = store.get_run(meta.run_id)
    if fresh is not None and fresh.status == RUN_STATUS_INTERRUPTED:
        if _assistant_reply_since_last_user(meta.session_id):
            return
    if _assistant_reply_since_last_user(meta.session_id):
        store.mark_status(meta.run_id, RUN_STATUS_INTERRUPTED)
        return
    user_key = get_session_store().user_key(meta.session_id)
    snap = store.get_snapshot(meta.run_id)
    body = build_run_stop_reply(
        INTERRUPT_REPLY,
        user_key=user_key,
        stream_markdown=snap.last_markdown,
        batch_line=snap.last_batch_line,
        external_line=snap.last_external_line,
    )
    body = finalize_web_reply_text(
        body,
        0.0,
        task_kind=classify_task_kind(meta.message),
        prompt=meta.message,
        reply_mode=meta.reply_mode,
        user_key=user_key,
    )
    get_session_store().append_message(meta.session_id, "assistant", body)
    store.append_event(meta.run_id, {"type": "done", "text": body})
    store.mark_status(meta.run_id, RUN_STATUS_INTERRUPTED)
    if not snap.final_text:
        store.update_snapshot(meta.run_id, {"type": "done", "text": body})


def _finalize_orphan_run(meta: RunMeta) -> None:
    """worker 已退出但 meta 仍为 running 时落盘结束态，便于前端拉消息。"""
    store = get_run_store()
    fresh = store.get_run(meta.run_id)
    if fresh is None or fresh.status != RUN_STATUS_RUNNING:
        return
    if store.is_worker_alive(meta.run_id):
        return
    if _run_cancelled_or_interrupted(meta):
        _finalize_cancelled_run(meta)
        return
    snap = store.get_snapshot(meta.run_id)
    if snap.final_text and not str(snap.final_text).lstrip().startswith("⚠️"):
        store.mark_status(meta.run_id, RUN_STATUS_DONE)
        return
    if _run_has_persisted_reply(meta):
        store.mark_status(meta.run_id, RUN_STATUS_DONE)
        return
    if _assistant_reply_since_last_user(meta.session_id):
        store.mark_status(meta.run_id, RUN_STATUS_DONE)
        return
    user_key = get_session_store().user_key(meta.session_id)
    err_body = build_run_stop_reply(
        SERVICE_RESTART_HEADLINE,
        user_key=user_key,
        stream_markdown=snap.last_markdown,
        batch_line=snap.last_batch_line,
        external_line=snap.last_external_line,
    )
    err_text = finalize_web_reply_text(
        err_body,
        0.0,
        task_kind=classify_task_kind(meta.message),
        prompt=meta.message,
        reply_mode=meta.reply_mode,
        user_key=user_key,
    )
    session_store = get_session_store()
    if not session_store.replace_last_assistant_if_failure(meta.session_id, err_text):
        session_store.append_message(meta.session_id, "assistant", err_text)
    store.append_event(meta.run_id, {"type": "error", "message": "worker lost", "text": err_text})
    store.mark_status(meta.run_id, RUN_STATUS_ERROR)
    if not snap.final_text:
        store.update_snapshot(meta.run_id, {"type": "error", "message": "worker lost", "text": err_text})


def _start_run_worker(run_id: str) -> int:
    from web_run_executor import start_run_in_background

    return start_run_in_background(run_id)


def _start_run_event_tailer(run: ActiveRun, *, progress_stop: threading.Event) -> None:
    store = get_run_store()

    def tailer() -> None:
        idle_polls = 0
        while not progress_stop.is_set():
            events, _ = store.read_new_events(run.run_id)
            if events:
                idle_polls = 0
            else:
                idle_polls += 1
            for event in events:
                etype = event.get("type")
                if etype == "ack":
                    run.last_ack_line = str(event.get("line") or "")
                elif etype == "status":
                    if "elapsed_line" in event:
                        run.last_elapsed_line = str(event.get("elapsed_line") or "")
                    if "batch_line" in event:
                        run.last_batch_line = str(event.get("batch_line") or "")
                    if "external_line" in event:
                        run.last_external_line = str(event.get("external_line") or "")
                    if "phase_line" in event:
                        run.last_phase_line = str(event.get("phase_line") or "")
                elif etype == "delta":
                    markdown = event.get("markdown")
                    if markdown:
                        run.last_markdown = str(markdown)
                    proc = event.get("process")
                    if isinstance(proc, dict):
                        from web_run_store import _merge_process_payload, _process_has_stream_content

                        prev = run.last_process if isinstance(run.last_process, dict) else None
                        run.last_process = _merge_process_payload(prev, proc)
                        from web_run_store import resolve_process_phase_line

                        run.last_phase_line = resolve_process_phase_line(run.last_process)
                elif etype == "done":
                    if run.done.is_set():
                        continue
                    run.final_text = str(event.get("text") or "")
                    run.emit_event(event)
                    run.done.set()
                    RUN_MANAGER.release_session(run)
                    run.task_session.end()
                    progress_stop.set()
                    return
                elif etype == "error":
                    if run.done.is_set():
                        continue
                    run.error = str(event.get("message") or "")
                    run.final_text = str(event.get("text") or "")
                    run.emit_event(event)
                    run.done.set()
                    RUN_MANAGER.release_session(run)
                    run.task_session.end()
                    progress_stop.set()
                    return
                run.emit_event(event)
            meta = store.get_run(run.run_id)
            if meta is not None and meta.status != RUN_STATUS_RUNNING:
                if not run.done.is_set():
                    snap = store.get_snapshot(run.run_id)
                    _apply_snapshot_to_run(run, snap)
                    if run.error:
                        run.emit_event(
                            {
                                "type": "error",
                                "message": run.error,
                                "text": run.final_text,
                            }
                        )
                    else:
                        run.emit_event({"type": "done", "text": run.final_text})
                    run.done.set()
                    RUN_MANAGER.release_session(run)
                progress_stop.set()
                return
            if (
                meta is not None
                and not store.is_worker_alive(run.run_id)
            ):
                respawned = (
                    _try_respawn_recent_run(meta)
                    if _within_run_recovery_grace(meta)
                    else None
                )
                if respawned is not None and store.is_worker_alive(run.run_id):
                    continue
                if store.is_worker_alive(run.run_id):
                    continue
                _finalize_orphan_run(meta)
                snap = store.get_snapshot(run.run_id)
                _apply_snapshot_to_run(run, snap)
                if run.error:
                    run.emit_event(
                        {"type": "error", "message": run.error, "text": run.final_text}
                    )
                else:
                    run.emit_event({"type": "done", "text": run.final_text})
                run.done.set()
                RUN_MANAGER.release_session(run)
                progress_stop.set()
                return
            poll_s = SSE_POLL_S if events else min(1.0, SSE_POLL_S * (1 + idle_polls // 4))
            time.sleep(poll_s)

    threading.Thread(
        target=tailer,
        daemon=True,
        name=f"web-run-tail-{run.run_id}",
    ).start()


def sweep_stale_running_runs() -> int:
    """worker 已退出或僵尸时自动落盘结束态，避免前端一直「思考中」。"""
    store = get_run_store()
    finalized = 0
    for meta in store.list_active_runs():
        if meta.status != RUN_STATUS_RUNNING:
            continue
        if store.is_worker_alive(meta.run_id):
            continue
        if _within_run_recovery_grace(meta):
            continue
        _finalize_orphan_run(meta)
        finalized += 1
        logger.info(
            "自动结束卡死任务 run=%s session=%s worker_pid=%s",
            meta.run_id,
            meta.session_id,
            meta.worker_pid,
        )
    return finalized


def _start_stale_run_sweeper(*, interval_s: float = 30.0) -> None:
    def loop() -> None:
        while True:
            time.sleep(interval_s)
            try:
                sweep_stale_running_runs()
            except Exception as exc:  # noqa: BLE001
                logger.warning("卡死任务 sweep 失败: %s", exc)

    threading.Thread(
        target=loop,
        daemon=True,
        name="web-stale-run-sweeper",
    ).start()


def recover_active_runs_on_startup() -> None:
    store = get_run_store()
    store.cleanup_old_runs()
    for meta in store.list_active_runs():
        if RUN_MANAGER.find_active_by_session(meta.session_id) is not None:
            continue
        _recover_running_meta(meta, allow_fresh_spawn=True)
        refreshed = store.get_run(meta.run_id)
        if refreshed is not None and store.is_worker_alive(meta.run_id):
            logger.info(
                "恢复进行中任务 run=%s session=%s worker_pid=%s",
                meta.run_id,
                meta.session_id,
                refreshed.worker_pid,
            )
        elif refreshed is not None and refreshed.status != RUN_STATUS_RUNNING:
            logger.info("清理孤儿任务 run=%s session=%s", meta.run_id, meta.session_id)
        else:
            logger.info(
                "等待 worker 启动 run=%s session=%s（不重复 spawn）",
                meta.run_id,
                meta.session_id,
            )
    sweep_stale_running_runs()


def _active_run_session_ids() -> set[str]:
    """一次扫描活跃 run，供会话列表批量标记 running（避免 O(会话数×run 数)）。"""
    global _ACTIVE_RUN_IDS_CACHE
    now = time.monotonic()
    cached = _ACTIVE_RUN_IDS_CACHE
    if cached is not None and now - cached[0] < _ACTIVE_RUN_IDS_CACHE_TTL:
        return set(cached[1])

    ids = RUN_MANAGER.active_session_ids()
    store = get_run_store()
    for meta in store.list_active_runs():
        sid = (meta.session_id or "").strip()
        if not sid or sid in ids:
            continue
        pid = int(meta.worker_pid or 0)
        if pid > 0 and store.is_pid_alive(pid):
            ids.add(sid)
        elif store.is_worker_alive(meta.run_id):
            ids.add(sid)
    _ACTIVE_RUN_IDS_CACHE = (now, frozenset(ids))
    return set(ids)


_ACTIVE_RUN_IDS_CACHE: tuple[float, frozenset[str]] | None = None
_ACTIVE_RUN_IDS_CACHE_TTL = 2.5


def _invalidate_active_run_ids_cache() -> None:
    global _ACTIVE_RUN_IDS_CACHE
    _ACTIVE_RUN_IDS_CACHE = None


_LITE_SESSIONS_CACHE: dict[str, tuple[float, frozenset[str], str, dict[str, Any]]] = {}


def _build_lite_sessions_response(
    viewer_staff_id: str | None,
) -> tuple[str, dict[str, Any]]:
    """lite 轮询专用：跳过 derived meta 同步，并按 index mtime + 活跃 run 缓存响应。"""
    store = get_session_store()
    index_mtime = store.index_disk_mtime()
    active_session_ids = frozenset(_active_run_session_ids())
    cache_key = (viewer_staff_id or "").strip()
    cached = _LITE_SESSIONS_CACHE.get(cache_key)
    if (
        cached is not None
        and cached[0] == index_mtime
        and cached[1] == active_session_ids
    ):
        return cached[2], cached[3]

    items = store.list_sessions(enrich_names=False, sync_derived_meta=False, readonly=True)
    try:
        from dingtalk_user_lookup import collect_known_labels

        known = collect_known_labels(items)
    except Exception:  # noqa: BLE001
        known = {}
    sessions = sort_sessions_for_display([
        {
            **meta.to_dict(known_labels=known, viewer_staff_id=viewer_staff_id),
            "running": meta.id in active_session_ids,
        }
        for meta in items
    ])
    etag = compute_sessions_list_etag(sessions, scope="all", lite=True)
    payload: dict[str, Any] = {"sessions": sessions, "query": "", "scope": "all"}
    _LITE_SESSIONS_CACHE[cache_key] = (index_mtime, active_session_ids, etag, payload)
    return etag, payload


def _resolve_active_run_for_session(session_id: str) -> ActiveRun | None:
    run = RUN_MANAGER.find_active_by_session(session_id)
    if run is not None:
        return run
    store = get_run_store()
    meta = store.find_active_by_session(session_id)
    if meta is None:
        return None
    if store.is_worker_alive(meta.run_id):
        return _get_or_recover_run(meta.run_id)
    recovered = _recover_running_meta(meta, allow_fresh_spawn=True)
    if store.is_worker_alive(meta.run_id):
        return recovered
    return None


def _json_response(
    handler: SimpleHTTPRequestHandler,
    payload: object,
    status: int = 200,
    *,
    etag: str | None = None,
) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    if etag:
        handler.send_header("ETag", etag)
    handler.end_headers()
    handler.wfile.write(body)


def _respond_not_modified(handler: SimpleHTTPRequestHandler, *, etag: str | None = None) -> None:
    handler.send_response(HTTPStatus.NOT_MODIFIED)
    if etag:
        handler.send_header("ETag", etag)
    handler.end_headers()


def _if_none_match_satisfied(handler: SimpleHTTPRequestHandler, etag: str) -> bool:
    client_tag = (handler.headers.get("If-None-Match") or "").strip()
    return bool(client_tag) and client_tag == etag


def _read_raw_body(handler: SimpleHTTPRequestHandler) -> bytes:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    return handler.rfile.read(length) if length > 0 else b""


def _handle_service_agent_webhook_post(handler: SimpleHTTPRequestHandler) -> None:
    body_bytes = _read_raw_body(handler)
    signature = handler.headers.get(SIGNATURE_HEADER) or ""
    status, payload = handle_webhook_body(body_bytes, signature)
    return _json_response(handler, payload, status)


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
    session_id: str = "",
) -> None:
    """每秒推送已用时与批量进度（与钉钉流式卡片三通道一致）。"""
    task_kind = classify_task_kind(message)
    estimate_s = resolve_task_estimate_seconds(task_kind, prompt=message)
    if session_id and should_rotate_cursor_agent(session_id) and estimate_s is not None:
        estimate_s = max(estimate_s, 240.0)
    ack_line = build_task_ack_message(
        _task_summary(message),
        prompt=message,
        estimate_s=estimate_s,
    )
    run.emit_event({"type": "ack", "line": ack_line})
    store = get_run_store()

    def emit_progress_status() -> None:
        elapsed = max(0.0, time.monotonic() - started_at)
        elapsed_line = _build_web_elapsed_status_line(elapsed)
        # 进度文件在两次 report 之间可能短暂不可读；保留上次文案，避免 Web 批量行闪烁。
        batch_line = run.last_batch_line
        state = read_batch_progress(user_key)
        if state is not None:
            batch_line = build_batch_progress_message(state)
        external_state = read_external_agent_progress(user_key)
        external_line = run.last_external_line
        if external_state is not None:
            external_line = build_external_agent_progress_message(external_state)
        run.emit_event(
            {
                "type": "status",
                "elapsed_line": elapsed_line,
                "batch_line": batch_line,
                "external_line": external_line,
                "phase_line": run.last_phase_line,
            }
        )

    def loop() -> None:
        emit_progress_status()
        while not progress_stop.wait(PROGRESS_TICK_S):
            if run.done.is_set():
                return
            emit_progress_status()

    threading.Thread(
        target=loop,
        daemon=True,
        name=f"web-progress-{run.run_id}",
    ).start()


def _session_owner_context(user: Any) -> tuple[str, str, float]:
    if user is None:
        return "", "", 0.0
    uid = str(getattr(user, "staff_id", "") or "").strip()
    label = lookup_auth_user_display_name(
        uid,
        str(getattr(user, "display_name", "") or "").strip(),
    )
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
    author_id: str = "",
    author_label: str = "",
    push_result_to_dingtalk: bool = False,
    push_dingtalk_staff_id: str = "",
    reply_mode: str | None = None,
) -> ActiveRun:
    store = get_session_store()
    run_store = get_run_store()
    user_key = store.user_key(session_id)
    task_kind = classify_task_kind(message)
    attachment_list = list(attachments or [])
    local_image_paths: list[str] = []
    local_file_paths: list[str] = []
    for item in attachment_list:
        local = local_path_from_api_path(item.api_path)
        if local is None:
            raise ValueError(f"附件不存在: {item.api_path}")
        if item.kind == "image":
            local_image_paths.append(str(local))
        else:
            local_file_paths.append(str(local))

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
        author_id=author_id,
        author_label=author_label,
    )
    if existing_run is not None:
        run = existing_run
    else:
        run = RUN_MANAGER.create(session_id)

    _supersede_prior_session_runs(session_id, keep_run_id=run.run_id)

    agent_model = _resolve_agent_model(model)
    external_ids = list(enabled_external_agents or [])
    normalized_reply_mode = normalize_reply_mode(reply_mode)
    run_store.create_run(
        RunMeta(
            run_id=run.run_id,
            session_id=session_id,
            message=message,
            display_message=display_message,
            model=agent_model,
            enabled_external_agents=external_ids,
            author_id=author_id,
            author_label=author_label,
            image_paths=local_image_paths,
            file_paths=local_file_paths,
            attachment_names=[item.original_name for item in attachment_list],
            worker_pid=0,
            status=RUN_STATUS_RUNNING,
            started_at=time.time(),
            push_result_to_dingtalk=bool(push_result_to_dingtalk),
            push_dingtalk_staff_id=(push_dingtalk_staff_id or "").strip(),
            reply_mode=normalized_reply_mode,
        )
    )
    run_timeout_s = resolve_agent_timeout_s(
        is_admin=is_web_admin(staff_id=author_id or None),
    )
    run.task_session.begin(
        message or display_message,
        conversation_id=user_key,
        budget_s=float(run_timeout_s),
    )
    clear_batch_progress(user_key)
    clear_batch_result(user_key)
    clear_service_agent_run_log(user_key)
    clear_external_agent_progress(user_key)
    started_at = time.monotonic()
    run.started_at = started_at
    run.task_kind = task_kind
    run.reply_mode = normalized_reply_mode
    progress_stop = threading.Event()
    _start_run_progress_watcher(
        run,
        user_key=user_key,
        message=message,
        started_at=started_at,
        progress_stop=progress_stop,
        session_id=session_id,
    )
    _start_run_worker(run.run_id)
    _start_run_event_tailer(run, progress_stop=progress_stop)
    run.tailers_attached = True
    return run


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def _content_type_with_charset(content_type: str) -> str:
    ct = (content_type or "application/octet-stream").strip()
    if ct.lower().startswith("text/") and "charset=" not in ct.lower():
        return f"{ct}; charset=utf-8"
    return ct


class WebAgentHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEB_AGENT_DIR), **kwargs)

    def _serve_static_file(
        self,
        target: Path,
        *,
        not_found_msg: str = "Not Found",
        inject_analytics: bool = False,
    ) -> None:
        if not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, not_found_msg)
            return
        content_type, _ = mimetypes.guess_type(str(target))
        if not content_type:
            content_type = "application/octet-stream"
        content_type = _content_type_with_charset(content_type)
        data = target.read_bytes()
        if inject_analytics and target.suffix.lower() in {".html", ".htm"}:
            try:
                data = _inject_analytics_script(data.decode("utf-8")).encode("utf-8")
            except UnicodeDecodeError:
                pass
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if target.suffix.lower() in {".html", ".htm"}:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _serve_family_pk_export(self, rel_path: str) -> None:
        root = FAMILY_PK_EXPORTS_DIR.resolve()
        target = (root / rel_path).resolve()
        if not str(target).startswith(str(root)):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._serve_static_file(
            target,
            inject_analytics=target.suffix.lower() in {".html", ".htm"},
        )

    def _serve_platform_guide(self, rel_path: str) -> None:
        root = PLATFORM_GUIDE_DIR.resolve()
        target = (root / rel_path).resolve()
        if not str(target).startswith(str(root)):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._serve_static_file(
            target,
            not_found_msg="platform guide not found",
            inject_analytics=target.suffix.lower() in {".html", ".htm"},
        )

    def _serve_keynote_preview(self) -> None:
        self._serve_static_file(
            KEYNOTE_PREVIEW_HTML,
            not_found_msg="keynote preview not found",
            inject_analytics=True,
        )

    def _serve_keynote_file(self, rel_path: str) -> None:
        root = KEYNOTE_DIR.resolve()
        target = (root / rel_path).resolve()
        if not str(target).startswith(str(root)):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._serve_static_file(
            target,
            not_found_msg="keynote file not found",
            inject_analytics=target.suffix.lower() in {".html", ".htm"},
        )

    def log_message(self, fmt: str, *args: Any) -> None:
        if self.path.startswith("/api/"):
            super().log_message(fmt, *args)

    def end_headers(self) -> None:
        path = urlparse(self.path).path
        if not path.startswith("/api/") and path.rsplit(".", 1)[-1].lower() in {
            "js",
            "html",
            "htm",
        }:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
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
        raw_path = parsed.path or "/"
        if raw_path == PLATFORM_GUIDE_URL_PREFIX:
            self.send_response(HTTPStatus.MOVED_PERMANENTLY)
            self.send_header("Location", f"{PLATFORM_GUIDE_URL_PREFIX}/")
            self.end_headers()
            return
        if raw_path == SHOWCASE_URL_PREFIX:
            self.send_response(HTTPStatus.MOVED_PERMANENTLY)
            self.send_header("Location", f"{SHOWCASE_URL_PREFIX}/")
            self.end_headers()
            return
        path = raw_path.rstrip("/") or "/"

        if path in ("/login.html", "/login"):
            self.path = "/login.html"
            return super().do_GET()

        if path in ("/theme.js", "/dingtalk_oauth.js", "/analytics.js"):
            return super().do_GET()

        # 页面依赖的静态脚本须免鉴权，否则浏览器可能收到 login.html 导致 JS 全局变量未定义
        if path.endswith(".js") and not path.startswith("/api/"):
            return super().do_GET()

        if path.startswith("/assets/"):
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
                admin = is_web_admin(staff_id=user.staff_id)
                user_payload: dict[str, Any] = {
                    "staffId": user.staff_id,
                    "displayName": lookup_auth_user_display_name(
                        user.staff_id, user.display_name
                    ),
                    "isAdmin": admin,
                    "isSuperAdmin": is_super_admin(user.staff_id) if admin else False,
                }
                if not admin:
                    user_payload["adminApplyStatus"] = application_status_for_staff(
                        user.staff_id
                    )
                payload["user"] = user_payload
            return _json_response(self, payload)

        if path == "/api/auth/dingtalk-config":
            return _json_response(self, dingtalk_oauth_public_config())

        if path == "/api/admin/apply/status":
            user = current_web_user(self)
            if user is None:
                return _json_response(self, {"error": "未登录"}, 401)
            if is_web_admin(staff_id=user.staff_id):
                return _json_response(self, {"status": "approved", "isAdmin": True})
            return _json_response(
                self,
                application_status_for_staff(user.staff_id),
            )

        if path == "/api/admin/users":
            user = current_web_user(self)
            if user is None:
                return _json_response(self, {"error": "未登录"}, 401)
            return _json_response(
                self,
                list_admin_users(
                    viewer_staff_id=user.staff_id,
                    viewer_display_name=lookup_auth_user_display_name(
                        user.staff_id, user.display_name
                    ),
                ),
            )

        if not authorize_request(self, method="GET"):
            return

        if path == "/":
            self.path = "/chat.html"
            return super().do_GET()

        if path == KEYNOTE_URL_PREFIX or path == f"{KEYNOTE_URL_PREFIX}/":
            return self._serve_keynote_preview()

        if path in (f"{KEYNOTE_URL_PREFIX}/promo", f"{KEYNOTE_URL_PREFIX}/promo/"):
            return self._serve_keynote_preview()

        if path == "/api/analytics/stats":
            viewer = current_web_user(self)
            if viewer is None or not is_web_admin(staff_id=viewer.staff_id):
                return _json_response(self, {"error": web_admin_denial_message()}, 403)
            qs = parse_qs(parsed.query)
            try:
                days = int(str((qs.get("days") or ["30"])[0]).strip() or "30")
            except ValueError:
                days = 30
            try:
                limit = int(str((qs.get("limit") or ["100"])[0]).strip() or "100")
            except ValueError:
                limit = 100
            return _json_response(
                self,
                get_analytics_store().summarize(days=days, limit=limit),
            )

        if path == "/api/usage/me/bounds":
            viewer = current_web_user(self)
            if viewer is None:
                return _json_response(self, {"error": "请先登录"}, 401)
            return _json_response(self, get_usage_date_bounds(viewer.staff_id))

        if path == "/api/usage/me":
            viewer = current_web_user(self)
            if viewer is None:
                return _json_response(self, {"error": "请先登录"}, 401)
            qs = parse_qs(parsed.query)
            range_key = str((qs.get("range") or ["day"])[0]).strip() or "day"
            start_date = str((qs.get("startDate") or [""])[0]).strip()
            end_date = str((qs.get("endDate") or [""])[0]).strip()
            refresh_raw = str((qs.get("refresh") or ["0"])[0]).strip().lower()
            refresh = refresh_raw in ("1", "true", "yes")
            try:
                if start_date and end_date:
                    payload = summarize_cursor_user_usage(
                        viewer.staff_id,
                        start_date=start_date,
                        end_date=end_date,
                        refresh=refresh,
                    )
                else:
                    payload = summarize_cursor_user_usage(
                        viewer.staff_id,
                        range_key=range_key,
                        refresh=refresh,
                    )
            except ValueError as exc:
                return _json_response(self, {"error": str(exc)}, 400)
            return _json_response(self, payload)

        if path == "/api/usage/cursor-session":
            viewer = current_web_user(self)
            if viewer is None:
                return _json_response(self, {"error": "请先登录"}, 401)
            return _json_response(
                self,
                get_cursor_usage_store().status_for_staff(viewer.staff_id),
            )

        if path == f"{KEYNOTE_URL_PREFIX}/speech_scripts":
            return self._serve_keynote_file("speech_scripts.html")

        if path == f"{KEYNOTE_URL_PREFIX}/pk-atm-guide":
            return self._serve_keynote_file("pk_atm_guide.html")

        if path.startswith(f"{KEYNOTE_URL_PREFIX}/"):
            rel = path[len(KEYNOTE_URL_PREFIX) :].lstrip("/")
            return self._serve_keynote_file(rel)

        if path == SHOWCASE_URL_PREFIX or path.startswith(f"{SHOWCASE_URL_PREFIX}/"):
            rel = path[len(SHOWCASE_URL_PREFIX) :].lstrip("/") or "index.html"
            return self._serve_family_pk_export(rel)

        if path == PLATFORM_GUIDE_URL_PREFIX or path.startswith(
            f"{PLATFORM_GUIDE_URL_PREFIX}/"
        ):
            rel = path[len(PLATFORM_GUIDE_URL_PREFIX) :].lstrip("/") or "index.html"
            return self._serve_platform_guide(rel)

        if path == "/api/meta":
            return _json_response(self, _platform_meta())

        if path == "/api/catalog":
            try:
                data = _load_catalog_data_cached()
                etag = compute_sessions_list_etag(
                    [{"id": "catalog", "updated_at": _catalog_sources_fingerprint()}],
                )
                if _if_none_match_satisfied(self, etag):
                    return _respond_not_modified(self, etag=etag)
                return _json_response(self, data, etag=etag)
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

        if path == "/api/web-docs":
            return _json_response(self, _load_web_docs())

        if path == "/api/web-users":
            # 分享/协作选人列表：/api/sessions 轮询已做增量同步，此处跳过以免阻塞弹窗
            store = get_session_store()
            store.reload_from_disk()
            viewer = current_web_user(self)
            include_self_raw = (parse_qs(parsed.query).get("include_self") or ["0"])[0].strip().lower()
            include_self = include_self_raw in ("1", "true", "yes")
            exclude = "" if include_self else (viewer.staff_id if viewer is not None else "")
            query = (parse_qs(parsed.query).get("q") or [""])[0]
            try:
                from dingtalk_user_lookup import (
                    list_selectable_group_chats,
                    list_selectable_staff_users,
                )

                users = enrich_selectable_users_with_admin_roles(
                    list_selectable_staff_users(
                        store.list_sessions(enrich_names=False),
                        exclude_staff_id=exclude,
                        exclude_localhost_admin=include_self,
                        query=query,
                        try_api_for_ascii=False,
                    )
                )
                groups = list_selectable_group_chats(
                    store.list_sessions(enrich_names=False),
                    query=query,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("列出可选人员失败: %s", exc)
                users = []
                groups = []
            return _json_response(
                self,
                {"users": users, "groups": groups, "total": len(users) + len(groups)},
            )

        if path == "/api/sessions":
            qs = parse_qs(parsed.query)
            lite_raw = (qs.get("lite") or ["0"])[0].strip().lower()
            lite = lite_raw in ("1", "true", "yes")
            if not lite:
                _maybe_sync_conversations(parsed)
            store = get_session_store()
            viewer = current_web_user(self)
            viewer_staff_id = viewer.staff_id if viewer is not None else None
            search_q = (qs.get("q") or [""])[0].strip()
            scope = (qs.get("scope") or ["all"])[0].strip().lower()
            if lite and not search_q and scope == "all":
                etag, payload = _build_lite_sessions_response(viewer_staff_id)
                if _if_none_match_satisfied(self, etag):
                    return _respond_not_modified(self, etag=etag)
                return _json_response(self, payload, etag=etag)
            items = store.list_sessions(enrich_names=False, sync_derived_meta=not lite)
            try:
                from dingtalk_user_lookup import collect_all_staff_labels, collect_known_labels

                if lite:
                    known = collect_known_labels(items)
                else:
                    known = collect_all_staff_labels(items, try_api_for_ascii=not lite)
            except Exception:  # noqa: BLE001
                known = {}
            items = filter_sessions_by_scope(
                items,
                scope,
                viewer_staff_id=viewer_staff_id,
            )
            if search_q:
                pairs = filter_sessions_by_search(
                    items,
                    search_q,
                    load_messages=store.get_all_messages,
                    load_search_entries=store.get_search_entries,
                    known_labels=known,
                )
            else:
                pairs = [(meta, None) for meta in items]
            active_session_ids = _active_run_session_ids()
            sessions = sort_sessions_for_display([
                {
                    **meta.to_dict(known_labels=known, viewer_staff_id=viewer_staff_id),
                    "running": meta.id in active_session_ids,
                    **(
                        {
                            "search_snippet": hit.snippet,
                            "search_message_timestamp": hit.message_timestamp,
                        }
                        if hit and hit.snippet
                        else {}
                    ),
                }
                for meta, hit in pairs
            ])
            etag = compute_sessions_list_etag(
                sessions,
                query=search_q,
                scope=scope,
                lite=lite,
            )
            if _if_none_match_satisfied(self, etag):
                return _respond_not_modified(self, etag=etag)
            return _json_response(
                self,
                {"sessions": sessions, "query": search_q, "scope": scope},
                etag=etag,
            )

        m = re.match(rf"^/api/sessions/({SESSION_ID_PATTERN})/active-run$", path)
        if m:
            session_id = m.group(1)
            store = get_session_store()
            if store.get_session(session_id) is None:
                return _json_response(self, {"error": "session not found"}, 404)

            client_tag = (self.headers.get("If-None-Match") or "").strip()
            run = RUN_MANAGER.find_active_by_session(session_id)
            if run is not None:
                payload = run.to_active_run_dict()
                etag = compute_active_run_etag(session_id, payload)
                if client_tag and client_tag == etag:
                    return _respond_not_modified(self, etag=etag)
                return _json_response(self, payload, etag=etag)

            inactive_etag = compute_active_run_etag(session_id, {"active": False})
            if client_tag and client_tag == inactive_etag:
                run_store = get_run_store()
                if run_store.find_active_by_session(session_id) is None:
                    return _respond_not_modified(self, etag=inactive_etag)

            run = _resolve_active_run_for_session(session_id)
            if run is None:
                payload = {"active": False}
                etag = compute_active_run_etag(session_id, payload)
                if _if_none_match_satisfied(self, etag):
                    return _respond_not_modified(self, etag=etag)
                return _json_response(self, payload, etag=etag)
            payload = run.to_active_run_dict()
            etag = compute_active_run_etag(session_id, payload)
            if _if_none_match_satisfied(self, etag):
                return _respond_not_modified(self, etag=etag)
            return _json_response(self, payload, etag=etag)

        m = re.match(rf"^/api/sessions/({SESSION_ID_PATTERN})/messages$", path)
        if m:
            session_id = m.group(1)
            store = get_session_store()
            session_meta = store.get_session(session_id)
            if session_meta is None:
                return _json_response(self, {"error": "session not found"}, 404)
            qs = parse_qs(parsed.query)
            tail_raw = (qs.get("tail") or [""])[0].strip()
            before = (qs.get("before") or [""])[0].strip()
            limit_raw = (qs.get("limit") or [""])[0].strip()
            tail = int(tail_raw) if tail_raw.isdigit() else None
            limit = int(limit_raw) if limit_raw.isdigit() else None
            messages_mtime = (
                float(session_meta.messages_mtime)
                if session_meta.messages_mtime > 0
                else 0.0
            )
            page_meta_est = estimate_messages_page_meta(
                session_meta.message_count,
                tail=tail,
                before=before or "",
                limit=limit,
            )
            if page_meta_est is not None and messages_mtime > 0:
                meta_etag = compute_messages_page_etag(
                    session_id,
                    messages_mtime=messages_mtime,
                    message_count=session_meta.message_count,
                    tail=tail,
                    before=before or "",
                    limit=limit,
                    total=int(page_meta_est["total"]),
                    has_older=bool(page_meta_est["has_older"]),
                    offset=int(page_meta_est["offset"]),
                )
                if _if_none_match_satisfied(self, meta_etag):
                    return _respond_not_modified(self, etag=meta_etag)
            slice_msgs, page_meta = store.get_messages(
                session_id,
                tail=tail,
                before=before or None,
                limit=limit,
            )
            author_sessions = (
                store.list_sessions(
                    enrich_names=False,
                    sync_derived_meta=False,
                    readonly=True,
                )
                if session_meta.source == "dingtalk"
                else None
            )
            messages = []
            for msg in slice_msgs:
                item: dict[str, object] = {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                }
                if msg.images:
                    item["images"] = msg.images
                if msg.files:
                    item["files"] = msg.files
                if msg.role == "user":
                    author_id, author_label = resolve_user_message_author(
                        msg,
                        session_meta,
                        sessions=author_sessions,
                    )
                    if author_id:
                        item["author_id"] = author_id
                    if author_label:
                        item["author_label"] = author_label
                else:
                    if msg.author_id:
                        item["author_id"] = msg.author_id
                    if msg.author_label:
                        item["author_label"] = msg.author_label
                messages.append(item)
            payload: dict[str, object] = {
                "messages": messages,
                "total": page_meta.get("total", len(messages)),
                "has_older": bool(page_meta.get("has_older")),
                "offset": int(page_meta.get("offset") or 0),
            }
            if messages_mtime > 0:
                payload["messages_mtime"] = messages_mtime
            etag = compute_messages_page_etag(
                session_id,
                messages_mtime=messages_mtime,
                message_count=session_meta.message_count,
                tail=tail,
                before=before or "",
                limit=limit,
                total=int(page_meta.get("total") or len(messages)),
                has_older=bool(page_meta.get("has_older")),
                offset=int(page_meta.get("offset") or 0),
            )
            if _if_none_match_satisfied(self, etag):
                return _respond_not_modified(self, etag=etag)
            return _json_response(self, payload, etag=etag)

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
        run = _get_or_recover_run(run_id)
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
                _record_analytics(
                    self,
                    event="login_fail",
                    page="/login.html",
                    props={"method": "otp"},
                )
                return _json_response(self, {"error": err or "登录失败"}, 401)
            _record_analytics(
                self,
                event="login_success",
                page="/login.html",
                props={"method": "otp"},
            )
            payload = {
                "ok": True,
                "user": {
                    "staffId": user.staff_id,
                    "displayName": lookup_auth_user_display_name(
                        user.staff_id, user.display_name
                    ),
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
                _record_analytics(
                    self,
                    event="login_fail",
                    page="/login.html",
                    props={"method": "dingtalk_oauth"},
                )
                return _json_response(self, {"error": err or "钉钉登录失败"}, 401)
            _record_analytics(
                self,
                event="login_success",
                page="/login.html",
                props={"method": "dingtalk_oauth"},
            )
            payload = {
                "ok": True,
                "user": {
                    "staffId": user.staff_id,
                    "displayName": lookup_auth_user_display_name(
                        user.staff_id, user.display_name
                    ),
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
            _record_analytics(self, event="logout", page="/chat.html")
            logout_current_session(self)
            return _json_response(self, {"ok": True})

        if path == "/api/admin/apply":
            user = current_web_user(self)
            if user is None:
                return _json_response(self, {"error": "未登录"}, 401)
            if is_web_admin(staff_id=user.staff_id):
                return _json_response(self, {"error": "你已是管理员"}, 400)
            result, err = submit_application(
                staff_id=user.staff_id,
                display_name=lookup_auth_user_display_name(
                    user.staff_id, user.display_name
                ),
            )
            if result is None:
                return _json_response(self, {"error": err or "申请失败"}, 400)
            status = application_status_for_staff(user.staff_id)
            payload: dict[str, Any] = {
                "ok": True,
                "status": status,
                "notified": bool(result.get("notified")),
                "skippedDuplicate": bool(result.get("skippedDuplicate")),
            }
            if err:
                payload["warning"] = err
            return _json_response(self, payload)

        if path == "/api/admin/quit":
            user = current_web_user(self)
            if user is None:
                return _json_response(self, {"error": "未登录"}, 401)
            result, err = quit_admin_role(staff_id=user.staff_id)
            if err:
                code = 403 if err == "该账号不可退出管理员" else 400
                return _json_response(self, {"error": err}, code)
            assert result is not None
            return _json_response(self, {"ok": True, **result})

        if path == "/api/admin/users/set":
            user = current_web_user(self)
            if user is None:
                return _json_response(self, {"error": "未登录"}, 401)
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            target_staff_id = str(body.get("staffId") or "").strip()
            is_admin_raw = body.get("isAdmin")
            if not isinstance(is_admin_raw, bool):
                return _json_response(self, {"error": "isAdmin 须为布尔值"}, 400)
            result, err = set_admin_role(
                operator_staff_id=user.staff_id,
                operator_display_name=lookup_auth_user_display_name(
                    user.staff_id, user.display_name
                ),
                target_staff_id=target_staff_id,
                is_admin=is_admin_raw,
            )
            if err:
                code = 403 if err == "没有权限" else 400
                return _json_response(self, {"error": err}, code)
            assert result is not None
            return _json_response(self, {"ok": True, **result})

        if path == "/api/admin/users/permissions":
            user = current_web_user(self)
            if user is None:
                return _json_response(self, {"error": "未登录"}, 401)
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            target_staff_id = str(body.get("staffId") or "").strip()
            permissions_raw = body.get("permissions")
            if not isinstance(permissions_raw, dict):
                return _json_response(self, {"error": "permissions 须为对象"}, 400)
            permissions = {
                str(key): bool(value)
                for key, value in permissions_raw.items()
            }
            result, err = set_admin_permissions(
                operator_staff_id=user.staff_id,
                operator_display_name=lookup_auth_user_display_name(
                    user.staff_id, user.display_name
                ),
                target_staff_id=target_staff_id,
                permissions=permissions,
            )
            if err:
                code = 403 if err == "没有权限" else 400
                return _json_response(self, {"error": err}, code)
            assert result is not None
            return _json_response(self, {"ok": True, **result})

        if path == "/api/admin/users/remove":
            user = current_web_user(self)
            if user is None:
                return _json_response(self, {"error": "未登录"}, 401)
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            target_staff_id = str(body.get("staffId") or "").strip()
            result, err = remove_admin_list_user(
                operator_staff_id=user.staff_id,
                operator_display_name=lookup_auth_user_display_name(
                    user.staff_id, user.display_name
                ),
                target_staff_id=target_staff_id,
            )
            if err:
                code = 403 if err == "没有权限" else 400
                return _json_response(self, {"error": err}, code)
            assert result is not None
            return _json_response(self, {"ok": True, **result})

        if path == "/api/analytics/event":
            return _handle_analytics_event_post(self)

        if path == "/api/service-agent/webhook":
            return _handle_service_agent_webhook_post(self)

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
            _record_analytics(
                self,
                event="session_create",
                page="/chat.html",
                props={"session_id": meta.id},
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
            push_result_to_dingtalk = bool(body.get("push_result_to_dingtalk"))
            reply_mode = normalize_reply_mode(body.get("reply_mode"))
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
            author_id, author_label = _session_owner_from_user(viewer)
            push_dingtalk_staff_id = ""
            if push_result_to_dingtalk:
                if viewer is None or not (viewer.staff_id or "").strip():
                    return _json_response(
                        self,
                        {"error": "需要钉钉登录后才能推送结果到钉钉"},
                        400,
                    )
                push_dingtalk_staff_id = viewer.staff_id.strip()
            active = _resolve_active_run_for_session(session_id)
            if active is not None and not active.done.is_set():
                return _json_response(
                    self,
                    {
                        "error": "该会话仍有任务进行中，请等待完成或中断后重试",
                        "run_id": active.run_id,
                        "session_id": session_id,
                    },
                    409,
                )
            run = RUN_MANAGER.create(session_id)
            try:
                saved_attachments = save_chat_attachments(session_id, attachment_items)
            except FileUploadError as exc:
                run.done.set()
                RUN_MANAGER.release_session(run)
                return _json_response(self, {"error": str(exc)}, 400)
            try:
                _start_chat_run(
                    session_id,
                    message,
                    attachments=saved_attachments,
                    existing_run=run,
                    model=agent_model,
                    enabled_external_agents=enabled_external_agents,
                    author_id=author_id,
                    author_label=author_label,
                    push_result_to_dingtalk=push_result_to_dingtalk,
                    push_dingtalk_staff_id=push_dingtalk_staff_id,
                    reply_mode=reply_mode,
                )
            except Exception as exc:  # noqa: BLE001
                run.task_session.end()
                run.done.set()
                RUN_MANAGER.release_session(run)
                logger.exception("启动 Web chat 失败 session=%s", session_id)
                return _json_response(self, {"error": str(exc)}, 500)
            _record_analytics(
                self,
                event="chat_send",
                page="/chat.html",
                props={
                    "session_id": session_id,
                    "model": agent_model,
                    "external_agents": len(enabled_external_agents),
                    "attachments": len(saved_attachments),
                    "push_dingtalk": push_result_to_dingtalk,
                    "reply_mode": reply_mode,
                },
            )
            return _json_response(self, {"run_id": run.run_id, "session_id": session_id})

        if path == "/api/usage/cursor-session":
            viewer = current_web_user(self)
            if viewer is None:
                return _json_response(self, {"error": "请先登录"}, 401)
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            session_token = body.get("sessionToken")
            cursor_email = body.get("cursorEmail")
            if session_token is None and cursor_email is None:
                return _json_response(self, {"error": "请提供 sessionToken 或 cursorEmail"}, 400)
            try:
                parsed = parse_cursor_session_input(str(session_token or ""))
                normalized_token = parsed["sessionToken"] if session_token is not None else None
                parsed_team_id = parsed["teamId"] if session_token is not None else None
                parsed_workos_id = parsed["workosId"] if session_token is not None else None
                if normalized_token:
                    verify_session_token(
                        normalized_token,
                        team_id=parsed_team_id or "",
                        workos_id=parsed_workos_id or "",
                    )
                cred_store = get_cursor_usage_store()
                old_creds = cred_store.get_credentials(viewer.staff_id)
                status = cred_store.upsert(
                    viewer.staff_id,
                    session_token=normalized_token if session_token is not None else None,
                    cursor_email=str(cursor_email or "") if cursor_email is not None else None,
                    team_id=parsed_team_id if session_token is not None else None,
                    workos_id=parsed_workos_id if session_token is not None else None,
                )
                if should_clear_usage_cache_on_credential_update(
                    old_creds,
                    session_token=normalized_token if session_token is not None else None,
                    cursor_email=str(cursor_email or "") if cursor_email is not None else None,
                    team_id=parsed_team_id if session_token is not None else None,
                    workos_id=parsed_workos_id if session_token is not None else None,
                ):
                    clear_user_usage_daily_cache(viewer.staff_id)
                clear_user_today_live_cache(viewer.staff_id)
            except CursorAuthError as exc:
                return _json_response(self, {"error": str(exc)}, 400)
            except ValueError as exc:
                return _json_response(self, {"error": str(exc)}, 400)
            return _json_response(self, {"ok": True, **status})

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

        if path == "/api/messages/forward":
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            viewer = current_web_user(self)
            if viewer is None:
                return _json_response(self, {"error": "未登录"}, 401)
            text = str(body.get("text") or "").strip()
            message_role = str(body.get("message_role") or "").strip().lower()
            question_text = str(body.get("question_text") or "").strip()
            raw_ids = body.get("recipient_staff_ids")
            if not isinstance(raw_ids, list):
                raw_ids = []
            recipient_ids = [str(item).strip() for item in raw_ids if str(item).strip()]
            raw_group_ids = body.get("recipient_group_ids")
            if not isinstance(raw_group_ids, list):
                raw_group_ids = []
            recipient_group_ids = [
                str(item).strip() for item in raw_group_ids if str(item).strip()
            ]
            if not text:
                return _json_response(self, {"error": "消息内容为空"}, 400)
            if not recipient_ids and not recipient_group_ids:
                return _json_response(self, {"error": "请选择至少一位接收人或群聊"}, 400)
            store = get_session_store()
            store.reload_from_disk()
            try:
                from dingtalk_user_lookup import (
                    list_selectable_group_chats,
                    list_selectable_staff_users,
                )

                allowed_staff = {
                    user["staffId"]
                    for user in list_selectable_staff_users(
                        store.list_sessions(enrich_names=False),
                        try_api_for_ascii=False,
                        exclude_localhost_admin=True,
                    )
                }
                allowed_groups = {
                    group["conversationId"]
                    for group in list_selectable_group_chats(
                        store.list_sessions(enrich_names=False),
                    )
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning("校验分享接收人失败: %s", exc)
                allowed_staff = set()
                allowed_groups = set()
            invalid_staff = [uid for uid in recipient_ids if uid not in allowed_staff]
            invalid_groups = [
                gid for gid in recipient_group_ids if gid not in allowed_groups
            ]
            if invalid_staff or invalid_groups:
                return _json_response(
                    self,
                    {"error": "包含不可选的接收人或群聊，请刷新列表后重试"},
                    400,
                )
            sender_name = lookup_auth_user_display_name(
                viewer.staff_id,
                viewer.display_name,
            )
            try:
                from web_message_forward import forward_message_to_dingtalk

                result = forward_message_to_dingtalk(
                    recipient_ids,
                    text,
                    recipient_group_ids=recipient_group_ids,
                    sender_name=sender_name,
                    message_role=message_role,
                    question_text=question_text,
                )
            except ValueError as exc:
                return _json_response(self, {"error": str(exc)}, 400)
            except Exception as exc:  # noqa: BLE001
                logger.exception("消息分享钉钉异常")
                return _json_response(self, {"error": f"分享失败：{exc}"}, 500)
            if not result.get("ok", True):
                return _json_response(
                    self,
                    {
                        "error": str(result.get("error") or "分享失败"),
                        **result,
                    },
                    502,
                )
            _record_analytics(
                self,
                event="message_forward",
                page="/chat.html",
                props={
                    "sent_count": result.get("sent_count", 0),
                    "failed_count": result.get("failed_count", 0),
                    "recipient_count": len(recipient_ids) + len(recipient_group_ids),
                },
            )
            return _json_response(self, result)

        if path == "/api/chat/cancel":
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            run_id = str(body.get("run_id") or "").strip()
            session_id = str(body.get("session_id") or "").strip()
            run = _get_or_recover_run(run_id) if run_id else None
            if run is None and session_id:
                run = _resolve_active_run_for_session(session_id)
            if run is None:
                return _json_response(self, {"error": "run not found"}, 404)
            if not _interrupt_active_run(run):
                return _json_response(self, {"error": "当前任务无法中断"}, 409)
            _record_analytics(
                self,
                event="chat_cancel",
                page="/chat.html",
                props={"session_id": run.session_id, "run_id": run.run_id},
            )
            return _json_response(self, {"ok": True})

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_PUT(self) -> None:
        if not authorize_request(self, method="PUT"):
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        m_collab = re.match(
            rf"^/api/sessions/({SESSION_ID_PATTERN})/collaborators$",
            path,
        )
        if m_collab:
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            session_id = m_collab.group(1)
            viewer = current_web_user(self)
            if viewer is None:
                return _json_response(self, {"error": "unauthorized"}, 401)
            raw_ids = body.get("collaborator_ids")
            if not isinstance(raw_ids, list):
                raw_ids = []
            collaborator_ids = [str(item).strip() for item in raw_ids if str(item).strip()]
            store = get_session_store()
            ok, err = store.set_web_collaborators(
                session_id,
                owner_id=viewer.staff_id,
                collaborator_ids=collaborator_ids,
            )
            if not ok:
                status = 403 if err == "forbidden" else 404 if err == "session not found" else 400
                return _json_response(self, {"error": err or "failed"}, status)
            meta = store.get_session(session_id)
            if meta is None:
                return _json_response(self, {"error": "session not found"}, 404)
            try:
                from dingtalk_user_lookup import collect_all_staff_labels

                known = collect_all_staff_labels(store.list_sessions(enrich_names=False))
            except Exception:  # noqa: BLE001
                known = {}
            return _json_response(
                self,
                meta.to_dict(known_labels=known, viewer_staff_id=viewer.staff_id),
            )

        m_run_push = re.match(rf"^/api/runs/({SESSION_ID_PATTERN})/push-dingtalk$", path)
        if m_run_push:
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            run_id = m_run_push.group(1)
            push_result_to_dingtalk = bool(body.get("push_result_to_dingtalk"))
            viewer = current_web_user(self)
            if viewer is None or not (viewer.staff_id or "").strip():
                return _json_response(self, {"error": "unauthorized"}, 401)
            run_store = get_run_store()
            run_meta = run_store.get_run(run_id)
            if run_meta is None:
                return _json_response(self, {"error": "run not found"}, 404)
            session_store = get_session_store()
            if session_store.get_session(run_meta.session_id) is None:
                return _json_response(self, {"error": "session not found"}, 404)
            if session_store.is_read_only_for_viewer(
                run_meta.session_id,
                viewer.staff_id,
            ):
                return _json_response(self, {"error": "forbidden"}, 403)
            push_dingtalk_staff_id = ""
            if push_result_to_dingtalk:
                push_dingtalk_staff_id = viewer.staff_id.strip()
            run_store.update_meta(
                run_id,
                push_result_to_dingtalk=push_result_to_dingtalk,
                push_dingtalk_staff_id=push_dingtalk_staff_id,
            )
            return _json_response(
                self,
                {
                    "ok": True,
                    "run_id": run_id,
                    "push_result_to_dingtalk": push_result_to_dingtalk,
                },
            )

        m_pin = re.match(rf"^/api/sessions/({SESSION_ID_PATTERN})/pin$", path)
        if m_pin:
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            session_id = m_pin.group(1)
            viewer = current_web_user(self)
            if viewer is None:
                return _json_response(self, {"error": "unauthorized"}, 401)
            pinned = body.get("pinned")
            if not isinstance(pinned, bool):
                return _json_response(self, {"error": "pinned must be boolean"}, 400)
            store = get_session_store()
            ok, err = store.set_session_pinned(session_id, pinned=pinned)
            if not ok:
                status = 404 if err == "session not found" else 400
                return _json_response(self, {"error": err or "failed"}, status)
            meta = store.get_session(session_id)
            if meta is None:
                return _json_response(self, {"error": "session not found"}, 404)
            try:
                from dingtalk_user_lookup import collect_all_staff_labels

                known = collect_all_staff_labels(store.list_sessions(enrich_names=False))
            except Exception:  # noqa: BLE001
                known = {}
            return _json_response(
                self,
                meta.to_dict(known_labels=known, viewer_staff_id=viewer.staff_id),
            )

        m_title = re.match(rf"^/api/sessions/({SESSION_ID_PATTERN})/title$", path)
        if m_title:
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            session_id = m_title.group(1)
            viewer = current_web_user(self)
            if viewer is None:
                return _json_response(self, {"error": "unauthorized"}, 401)
            if "title" not in body:
                return _json_response(self, {"error": "title required"}, 400)
            title = str(body.get("title") or "")
            store = get_session_store()
            ok, err = store.set_session_custom_title(session_id, title=title)
            if not ok:
                status = 404 if err == "session not found" else 400
                return _json_response(self, {"error": err or "failed"}, status)
            meta = store.get_session(session_id)
            if meta is None:
                return _json_response(self, {"error": "session not found"}, 404)
            try:
                from dingtalk_user_lookup import collect_all_staff_labels

                known = collect_all_staff_labels(store.list_sessions(enrich_names=False))
            except Exception:  # noqa: BLE001
                known = {}
            return _json_response(
                self,
                meta.to_dict(known_labels=known, viewer_staff_id=viewer.staff_id),
            )

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

        if path == "/api/usage/cursor-session":
            viewer = current_web_user(self)
            if viewer is None:
                return _json_response(self, {"error": "请先登录"}, 401)
            status = get_cursor_usage_store().clear(viewer.staff_id)
            clear_user_usage_daily_cache(viewer.staff_id)
            clear_user_today_live_cache(viewer.staff_id)
            return _json_response(self, {"ok": True, **status})

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
    from web_run_executor import init_agent_runtime

    init_agent_runtime()
    recover_active_runs_on_startup()
    _start_stale_run_sweeper()
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
