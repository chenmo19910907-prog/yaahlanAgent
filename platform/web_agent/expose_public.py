#!/usr/bin/env python3
"""将 Web Agent 通过 Cloudflare Tunnel（或 ngrok）暴露到公网。

使用前须在 platform/dingtalk_gateway/.env.local 配置：
  WEB_AGENT_AUTH_USER=你的用户名
  WEB_AGENT_AUTH_PASSWORD=强密码

示例：
  python3 platform/web_agent/expose_public.py
  python3 platform/web_agent/expose_public.py --provider ngrok
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEB_AGENT_DIR.parent.parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from env_loader import ENV_LOCAL, load_env_local  # noqa: E402
from web_auth import auth_credentials, otp_auth_enabled  # noqa: E402

DEFAULT_PORT = 18766

TUNNEL_URL_RE = re.compile(
    r"https://[a-z0-9-]+\.(?:trycloudflare\.com|ngrok(?:-free)?\.app|ngrok\.io)"
)


def _load_config_port() -> int:
    cfg_path = WEB_AGENT_DIR / "config.json"
    if not cfg_path.is_file():
        return DEFAULT_PORT
    import json

    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        return int(data.get("port") or DEFAULT_PORT)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return DEFAULT_PORT


def _require_auth_configured() -> tuple[str, str] | None:
    load_env_local()
    if otp_auth_enabled():
        return None
    creds = auth_credentials()
    if creds is None:
        raise RuntimeError(
            "外网暴露须启用钉钉验证码登录（默认已开启），或在 "
            f"{ENV_LOCAL} 配置：\n"
            "  WEB_AGENT_AUTH_USER=你的用户名\n"
            "  WEB_AGENT_AUTH_PASSWORD=强密码\n"
            "若仅需 Basic Auth，可设 WEB_AGENT_OTP_AUTH=0"
        )
    return creds


def _find_binary(name: str) -> str | None:
    path = shutil.which(name)
    return path if path else None


def is_port_open(host: str, port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def _ensure_local_server(port: int) -> None:
    if is_port_open("127.0.0.1", port):
        print(f"Web Agent 已在运行：http://127.0.0.1:{port}/")
        return
    print("正在启动 Web Agent 服务…")
    subprocess.run(
        [sys.executable, str(WEB_AGENT_DIR / "server.py"), "--ensure"],
        cwd=str(REPO_ROOT),
        check=True,
    )
    if not is_port_open("127.0.0.1", port):
        raise RuntimeError("Web Agent 服务启动失败")
    print(f"Web Agent 已启动：http://127.0.0.1:{port}/")


def _spawn_tunnel(
    provider: str,
    port: int,
    *,
    detached: bool = False,
    log_path: Path | None = None,
) -> subprocess.Popen[str] | None:
    local_url = f"http://127.0.0.1:{port}"
    if provider == "cloudflare":
        binary = _find_binary("cloudflared")
        if not binary:
            raise RuntimeError(
                "未找到 cloudflared。安装：brew install cloudflared\n"
                "或使用：python3 platform/web_agent/expose_public.py --provider ngrok"
            )
        cmd = [binary, "tunnel", "--url", local_url, "--no-autoupdate"]
    elif provider == "ngrok":
        binary = _find_binary("ngrok")
        if not binary:
            raise RuntimeError("未找到 ngrok。安装：https://ngrok.com/download")
        cmd = [binary, "http", str(port), "--log", "stdout"]
    else:
        raise ValueError(f"未知 provider: {provider}")

    if detached:
        log_path = log_path or (WEB_AGENT_DIR / "data" / "tunnel.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("a", encoding="utf-8")
        subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        return None

    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def _wait_for_public_url(proc: subprocess.Popen[str], *, timeout_s: float = 45.0) -> str:
    deadline = time.monotonic() + timeout_s
    lines: list[str] = []
    url_holder: dict[str, str] = {}

    def reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line.rstrip())
            print(line, end="" if line.endswith("\n") else "\n")
            match = TUNNEL_URL_RE.search(line)
            if match:
                url_holder["url"] = match.group(0)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    while time.monotonic() < deadline:
        if url_holder.get("url"):
            return url_holder["url"]
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    tail = "\n".join(lines[-20:])
    raise RuntimeError(f"未在 {timeout_s:.0f}s 内获取公网 URL。\n最近输出：\n{tail}")


def _start_detached_tunnel_and_wait_url(
    provider: str,
    port: int,
    *,
    timeout_s: float = 45.0,
) -> str:
    log_path = WEB_AGENT_DIR / "data" / "tunnel.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")
    _spawn_tunnel(provider, port, detached=True, log_path=log_path)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if log_path.is_file():
            text = log_path.read_text(encoding="utf-8", errors="replace")
            match = TUNNEL_URL_RE.search(text)
            if match:
                return match.group(0)
        time.sleep(0.5)
    tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:] if log_path.is_file() else ""
    raise RuntimeError(f"未在 {timeout_s:.0f}s 内获取公网 URL。\n最近日志：\n{tail}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(description="将 Web Agent 暴露到公网（带鉴权）")
    parser.add_argument(
        "--provider",
        choices=("cloudflare", "ngrok"),
        default="cloudflare",
        help="隧道提供商（默认 cloudflare quick tunnel）",
    )
    parser.add_argument("--port", type=int, default=None, help="Web Agent 端口")
    parser.add_argument("--no-wait", action="store_true", help="打印 URL 后退出（隧道仍在后台）")
    args = parser.parse_args()

    port = args.port if args.port is not None else _load_config_port()
    _require_auth_configured()
    os.environ["WEB_AGENT_PUBLIC"] = "1"

    try:
        _ensure_local_server(port)
        print(f"\n正在启动 {args.provider} 隧道 → 127.0.0.1:{port} …", flush=True)
        if args.no_wait:
            public_url = _start_detached_tunnel_and_wait_url(args.provider, port)
            proc = None
        else:
            proc = _spawn_tunnel(args.provider, port)
            assert proc is not None
            public_url = _wait_for_public_url(proc)
    except KeyboardInterrupt:
        return 130
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr, flush=True)
        return 1

    url_file = WEB_AGENT_DIR / "data" / "public_url.txt"
    url_file.parent.mkdir(parents=True, exist_ok=True)
    url_file.write_text(public_url + "\n", encoding="utf-8")

    print("\n" + "=" * 60, flush=True)
    print("Web Agent 公网地址（已启用 HTTP 鉴权）：", flush=True)
    print(f"  {public_url}/", flush=True)
    print(f"\n登录用户名：{user}", flush=True)
    print("登录密码：见 .env.local 中 WEB_AGENT_AUTH_PASSWORD", flush=True)
    print("\n首次打开浏览器会弹出登录框；SSE 流式与 API 共用同一鉴权。", flush=True)
    if args.no_wait:
        print("隧道已在后台运行（日志：platform/web_agent/data/tunnel.log）。", flush=True)
    else:
        print("按 Ctrl+C 关闭隧道。", flush=True)
    print("=" * 60 + "\n", flush=True)

    if args.no_wait:
        return 0

    assert proc is not None

    def _shutdown(*_args: object) -> None:
        if proc.poll() is None:
            proc.terminate()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        while proc.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        _shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
