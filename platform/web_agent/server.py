#!/usr/bin/env python3
"""Web Agent HTTP 服务：托管 chat.html，提供聊天 API 与 SSE 流式输出。"""

from __future__ import annotations

import argparse
import json
import logging
import queue
import re
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
from urllib.parse import parse_qs, urlparse

WEB_AGENT_DIR = Path(__file__).resolve().parent
PLATFORM_DIR = WEB_AGENT_DIR.parent
REPO_ROOT = PLATFORM_DIR.parent
GATEWAY_DIR = PLATFORM_DIR / "dingtalk_gateway"
SCRIPTS_DIR = PLATFORM_DIR / "scripts"

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from chat_runner import run_web_chat  # noqa: E402
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
from web_session_store import get_session_store  # noqa: E402

logger = logging.getLogger("web-agent")

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 18766
CONFIG_PATH = WEB_AGENT_DIR / "config.json"
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


def _load_catalog_data() -> dict[str, Any]:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from generate_catalog import _load_catalog_data as load_data  # noqa: WPS433

    return load_data()


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
        "quickPrompts": cfg.get("quickPrompts") or [],
        "quickPromptCount": int(cfg.get("quickPromptCount") or 4),
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

    def _purge_old(self) -> None:
        if len(self._runs) <= 50:
            return
        done_ids = [rid for rid, r in self._runs.items() if r.done.is_set()]
        for rid in done_ids[: len(done_ids) - 20]:
            self._runs.pop(rid, None)


RUN_MANAGER = RunManager()


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
    run.events.put({"type": "ack", "line": ack_line})

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
            run.events.put(
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


def _start_chat_run(session_id: str, message: str) -> ActiveRun:
    store = get_session_store()
    user_key = store.user_key(session_id)
    task_kind = classify_task_kind(message)
    store.append_message(session_id, "user", message)
    run = RUN_MANAGER.create(session_id)
    clear_batch_progress(user_key)
    started_at = time.monotonic()
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
            run.events.put({"type": "delta", "markdown": markdown})

        try:
            final = run_web_chat(
                session_id,
                message,
                on_render=on_render,
                session_ctrl=run.task_session,
            )
            elapsed = time.monotonic() - started_at
            body = final or last_markdown
            run.final_text = append_duration_footer(body, elapsed, task_kind=task_kind)
            store.append_message(session_id, "assistant", run.final_text)
            status = "ok"
            run.events.put({"type": "done", "text": run.final_text})
        except TaskInterrupted:
            elapsed = time.monotonic() - started_at
            run.final_text = append_duration_footer(
                "⚠️ 任务已中断。",
                elapsed,
                task_kind=task_kind,
            )
            store.append_message(session_id, "assistant", run.final_text)
            status = "interrupted"
            run.events.put({"type": "done", "text": run.final_text})
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - started_at
            run.error = str(exc)
            logger.exception("Web chat run failed session=%s", session_id)
            run.final_text = append_duration_footer(
                f"⚠️ {run.error}",
                elapsed,
                task_kind=task_kind,
            )
            store.append_message(session_id, "assistant", run.final_text)
            run.events.put({"type": "error", "message": run.error, "text": run.final_text})
        finally:
            progress_stop.set()
            clear_batch_progress(user_key)
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

    def log_message(self, fmt: str, *args: Any) -> None:
        if self.path.startswith("/api/"):
            super().log_message(fmt, *args)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/":
            self.path = "/chat.html"
            return super().do_GET()

        if path == "/api/meta":
            return _json_response(self, _platform_meta())

        if path == "/api/catalog":
            try:
                return _json_response(self, _load_catalog_data())
            except (OSError, ValueError, FileNotFoundError) as exc:
                logger.exception("Failed to load catalog data")
                return _json_response(self, {"error": str(exc)}, 500)

        if path == "/api/sessions":
            sync_all_from_conversation_store()
            store = get_session_store()
            store.reload_from_disk()
            items = store.list_sessions()
            try:
                from dingtalk_user_lookup import collect_known_labels

                known = collect_known_labels(items)
            except Exception:  # noqa: BLE001
                known = {}
            sessions = [s.to_dict(known_labels=known) for s in items]
            return _json_response(self, {"sessions": sessions})

        m = re.match(rf"^/api/sessions/({SESSION_ID_PATTERN})/messages$", path)
        if m:
            session_id = m.group(1)
            store = get_session_store()
            if store.get_session(session_id) is None:
                return _json_response(self, {"error": "session not found"}, 404)
            messages = [
                {"role": msg.role, "content": msg.content, "timestamp": msg.timestamp}
                for msg in store.get_messages(session_id)
            ]
            return _json_response(self, {"messages": messages})

        m = re.match(r"^/api/chat/stream/([a-f0-9]+)$", path)
        if m:
            return self._handle_sse(m.group(1))

        return super().do_GET()

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
            while time.monotonic() < deadline:
                try:
                    event = run.events.get(timeout=SSE_POLL_S)
                except queue.Empty:
                    if run.done.is_set():
                        break
                    continue
                payload = json.dumps(event, ensure_ascii=False)
                chunk = f"data: {payload}\n\n".encode("utf-8")
                self.wfile.write(chunk)
                self.wfile.flush()
                if event.get("type") in ("done", "error"):
                    sent_done = True
                    break
            if not sent_done and run.done.is_set():
                if run.error:
                    payload = json.dumps({"type": "error", "message": run.error}, ensure_ascii=False)
                else:
                    payload = json.dumps({"type": "done", "text": run.final_text}, ensure_ascii=False)
                self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            run.task_session.request_cancel()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/sessions":
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            title = str(body.get("title") or "新对话")
            meta = get_session_store().create_session(title=title)
            return _json_response(self, meta.to_dict(), 201)

        if path == "/api/chat":
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            session_id = str(body.get("session_id") or "").strip()
            message = str(body.get("message") or "").strip()
            if not session_id or not message:
                return _json_response(self, {"error": "session_id and message required"}, 400)
            store = get_session_store()
            if store.get_session(session_id) is None:
                return _json_response(self, {"error": "session not found"}, 404)
            if store.is_read_only(session_id):
                return _json_response(
                    self,
                    {"error": "钉钉同步会话只读，请在 Web 新建对话继续"},
                    403,
                )
            run = _start_chat_run(session_id, message)
            return _json_response(self, {"run_id": run.run_id, "session_id": session_id})

        if path == "/api/chat/cancel":
            try:
                body = _read_json_body(self)
            except json.JSONDecodeError:
                return _json_response(self, {"error": "invalid json"}, 400)
            run_id = str(body.get("run_id") or "").strip()
            run = RUN_MANAGER.get(run_id)
            if run is None:
                return _json_response(self, {"error": "run not found"}, 404)
            run.task_session.request_cancel()
            return _json_response(self, {"ok": True})

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        m = re.match(rf"^/api/sessions/({SESSION_ID_PATTERN})$", parsed.path.rstrip("/"))
        if not m:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        ok = get_session_store().delete_session(m.group(1))
        if not ok:
            return _json_response(self, {"error": "session not found"}, 404)
        return _json_response(self, {"ok": True})


def serve(host: str, port: int) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = ThreadingHTTPServer((host, port), WebAgentHandler)
    print(f"Web Agent: http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def ensure_server(host: str | None = None, port: int | None = None, wait_s: float = 3.0) -> tuple[str, int]:
    cfg = _load_config()
    use_host = host or str(cfg.get("host") or DEFAULT_HOST)
    use_port = port if port is not None else int(cfg.get("port") or DEFAULT_PORT)
    check_host = "127.0.0.1" if use_host == "0.0.0.0" else use_host

    if is_port_open(check_host, use_port):
        return use_host, use_port

    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--serve", "--host", use_host, "--port", str(use_port)],
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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
    parser.add_argument("--ensure", action="store_true", help="若未运行则后台启动")
    parser.add_argument("--serve", action="store_true", help="前台运行 HTTP 服务")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    cfg = _load_config()
    host = args.host or str(cfg.get("host") or DEFAULT_HOST)
    port = args.port if args.port is not None else int(cfg.get("port") or DEFAULT_PORT)

    if args.ensure:
        ensure_server(host, port)
        display = "127.0.0.1" if host == "0.0.0.0" else host
        print(f"http://{display}:{port}/")
        return 0

    if args.serve:
        serve(host, port)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
