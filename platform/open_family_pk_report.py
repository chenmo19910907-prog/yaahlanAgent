#!/usr/bin/env python3
"""生成并打开工具平台驱动的复杂活动数据造表测试 Showcase 演示页。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "platform" / "family_pk_report"
GENERATOR = REPORT_DIR / "generate.py"
RENDER_MEDIA = REPORT_DIR / "scripts" / "render_demo_media.py"
WEB_AGENT_SERVER = REPO_ROOT / "platform" / "web_agent" / "server.py"
WEB_AGENT_CONFIG = REPO_ROOT / "platform" / "web_agent" / "config.json"
SHOWCASE_CONFIG = REPORT_DIR / "config" / "showcase.json"
EXPORTS_DIR = REPORT_DIR / "exports"
MEDIA_DIR = REPORT_DIR / "media"
SHOWCASE_PATH = "/family-pk-showcase/index.html"


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _web_agent_port() -> int:
    cfg = _load_json(WEB_AGENT_CONFIG)
    port = cfg.get("port")
    return int(port) if isinstance(port, int) and port > 0 else 18766


def _showcase_urls() -> tuple[str, str]:
    cfg = _load_json(SHOWCASE_CONFIG)
    local_base = str(cfg.get("webAgentLocalUrl") or "http://127.0.0.1:18766").strip().rstrip("/")
    remote_base = str(cfg.get("webAgentRemoteUrl") or cfg.get("webAgentUrl") or "").strip().rstrip("/")
    stamp = f"v={int(time.time())}"
    local_showcase = f"{local_base}{SHOWCASE_PATH}?{stamp}"
    remote_showcase = f"{remote_base}{SHOWCASE_PATH}?{stamp}" if remote_base else ""
    return local_showcase, remote_showcase


def _refresh_demo_media(*, required: bool) -> int:
    if not RENDER_MEDIA.is_file():
        print(f"missing: {RENDER_MEDIA}", file=sys.stderr)
        return 1 if required else 0

    rc = subprocess.call([sys.executable, str(RENDER_MEDIA)], cwd=str(REPO_ROOT))
    if rc == 0:
        return 0

    if required:
        return rc

    has_media = MEDIA_DIR.is_dir() and any(MEDIA_DIR.glob("*.svg"))
    print("warn: demo media refresh failed; using existing SVG files", file=sys.stderr)
    if not has_media:
        print(
            "error: no cached media/*.svg; install deps then retry:\n"
            "  pip install -r platform/dingtalk_gateway/requirements.txt",
            file=sys.stderr,
        )
        return rc
    print(
        "hint: pip install -r platform/dingtalk_gateway/requirements.txt "
        "· or run with --refresh-media after deps are ready",
        file=sys.stderr,
    )
    return 0


def _ensure_web_agent() -> str:
    if not WEB_AGENT_SERVER.is_file():
        hub = EXPORTS_DIR / "index.html"
        return hub.as_uri() if hub.is_file() else EXPORTS_DIR.as_uri()

    proc = subprocess.run(
        [sys.executable, str(WEB_AGENT_SERVER), "--ensure"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    base = proc.stdout.strip().splitlines()[-1].rstrip("/") if proc.returncode == 0 and proc.stdout.strip() else ""
    if not base:
        port = _web_agent_port()
        base = f"http://127.0.0.1:{port}"
    return base


def _warn_if_showcase_unavailable(agent_base: str) -> None:
    url = f"{agent_base.rstrip('/')}{SHOWCASE_PATH}"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            if resp.status == 200:
                return
    except (urllib.error.URLError, TimeoutError, ValueError):
        pass
    print(
        "warn: 演示页路由未就绪，请重启 Web Agent 后重试",
        file=sys.stderr,
    )
    print("      python3 platform/web_agent/server.py --serve", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成并打开复杂活动数据造表测试 Showcase")
    parser.add_argument(
        "--refresh-media",
        action="store_true",
        help="从钉钉表重新生成演示 SVG（需 httpx 与钉钉 Cookie）",
    )
    parser.add_argument(
        "--skip-media",
        action="store_true",
        help="跳过演示 SVG 刷新，直接使用 media/ 已有文件",
    )
    parser.add_argument(
        "--open-agent",
        action="store_true",
        help="同时打开 Web Agent 主页（本地工具平台输入框）",
    )
    args = parser.parse_args()

    if not GENERATOR.is_file():
        print(f"missing: {GENERATOR}", file=sys.stderr)
        return 1

    if not args.skip_media:
        rc = _refresh_demo_media(required=args.refresh_media)
        if rc != 0:
            return rc

    cmd = [sys.executable, str(GENERATOR), "--scan-tmp", "--hub"]
    rc = subprocess.call(cmd, cwd=str(REPO_ROOT))
    if rc != 0:
        return rc

    agent_base = _ensure_web_agent().rstrip("/")
    _warn_if_showcase_unavailable(agent_base)
    local_showcase, remote_showcase = _showcase_urls()
    if not local_showcase.startswith("http"):
        local_showcase = f"{agent_base}{SHOWCASE_PATH}?v={int(time.time())}"

    opened = local_showcase
    if webbrowser.open(opened):
        print(f"opened showcase: {opened}")
    else:
        print(f"showcase: {opened}")

    print(f"web agent: {agent_base}/")
    if remote_showcase:
        print(f"remote showcase: {remote_showcase}")

    if args.open_agent:
        agent_url = f"{agent_base}/?v={int(time.time())}"
        if webbrowser.open(agent_url):
            print(f"opened web agent: {agent_url}")
        else:
            print(f"web agent: {agent_url}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
