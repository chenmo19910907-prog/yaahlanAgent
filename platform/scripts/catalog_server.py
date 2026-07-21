#!/usr/bin/env python3
"""本地 HTTP 服务：托管 catalog.html，并提供 Cursor 提示语 bridge API。"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
PLATFORM_DIR = SCRIPT_DIR.parent
REPO_ROOT = PLATFORM_DIR.parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from cursor_bridge import send_prompt_to_cursor  # noqa: E402

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18765
SOURCES_PATH = PLATFORM_DIR / "config" / "sources.json"


def _read_bridge_config() -> tuple[str, int]:
    host = DEFAULT_HOST
    port = DEFAULT_PORT
    if SOURCES_PATH.is_file():
        with open(SOURCES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        bridge = data.get("cursor_bridge")
        if isinstance(bridge, dict):
            if isinstance(bridge.get("host"), str) and bridge["host"].strip():
                host = bridge["host"].strip()
            if isinstance(bridge.get("port"), int) and bridge["port"] > 0:
                port = bridge["port"]
    return host, port


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def catalog_url(host: str | None = None, port: int | None = None) -> str:
    cfg_host, cfg_port = _read_bridge_config()
    use_host = host or cfg_host
    use_port = port if port is not None else cfg_port
    return f"http://{use_host}:{use_port}/catalog.html"


class CatalogHandler(SimpleHTTPRequestHandler):
    repo_root: Path = REPO_ROOT

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(PLATFORM_DIR), **kwargs)

    def log_message(self, fmt: str, *args: Any) -> None:
        if self.path.startswith("/api/"):
            super().log_message(fmt, *args)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/ping":
            body = json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/cursor-prompt":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(raw.decode("utf-8") if raw else "{}")
        except json.JSONDecodeError:
            self.send_error(HTTPStatus.BAD_REQUEST, "invalid json")
            return

        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            self.send_error(HTTPStatus.BAD_REQUEST, "text required")
            return

        try:
            mode = send_prompt_to_cursor(text, self.repo_root)
        except OSError as exc:
            body = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.NOT_IMPLEMENTED)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        except (RuntimeError, ValueError) as exc:
            body = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        body = json.dumps({"ok": True, "mode": mode}, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def ensure_server(host: str | None = None, port: int | None = None, wait_s: float = 3.0) -> tuple[str, int]:
    cfg_host, cfg_port = _read_bridge_config()
    use_host = host or cfg_host
    use_port = port if port is not None else cfg_port

    if is_port_open(use_host, use_port):
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
        if is_port_open(use_host, use_port):
            return use_host, use_port
        if proc.poll() is not None:
            raise RuntimeError("catalog server 启动失败")
        time.sleep(0.1)

    raise RuntimeError("catalog server 启动超时")


def serve(host: str, port: int) -> None:
    CatalogHandler.repo_root = REPO_ROOT
    server = ThreadingHTTPServer((host, port), CatalogHandler)
    print(f"catalog server: http://{host}:{port}/catalog.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="工具平台 catalog 本地 HTTP 服务")
    parser.add_argument("--ensure", action="store_true", help="若未运行则后台启动服务后退出")
    parser.add_argument("--serve", action="store_true", help="前台运行 HTTP 服务")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    cfg_host, cfg_port = _read_bridge_config()
    host = args.host or cfg_host
    port = args.port if args.port is not None else cfg_port

    if args.ensure:
        ensure_server(host, port)
        print(catalog_url(host, port))
        return 0

    if args.serve:
        serve(host, port)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
