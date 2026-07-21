#!/usr/bin/env python3
"""本地 HTTP 服务：托管 family_pk_report/exports 演示页。"""

from __future__ import annotations

import argparse
import socket
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18767
REPORT_DIR = Path(__file__).resolve().parents[1]
EXPORTS_DIR = REPORT_DIR / "exports"


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def report_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return f"http://{host}:{port}/index.html"


class ReportHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(EXPORTS_DIR), **kwargs)

    def end_headers(self) -> None:
        if self.path.endswith(".html") or self.path.endswith("/") or self.path == "/index.html":
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:
        if args and "404" in str(args[1]):
            super().log_message(fmt, *args)


def main() -> int:
    parser = argparse.ArgumentParser(description="family_pk_report exports HTTP server")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--ensure", action="store_true", help="若端口已占用则直接输出 URL")
    args = parser.parse_args()

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    url = report_url(args.host, args.port)

    if args.ensure and is_port_open(args.host, args.port):
        print(url)
        return 0

    server = ThreadingHTTPServer((args.host, args.port), ReportHandler)
    print(url, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
