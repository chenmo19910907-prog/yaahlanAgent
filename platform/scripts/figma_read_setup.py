#!/usr/bin/env python3
"""配置 Web Agent / 钉钉网关用的 figma-read MCP（FIGMA Personal Access Token）。"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATEWAY_VENV_PY = REPO_ROOT / "platform" / "dingtalk_gateway" / ".venv" / "bin" / "python3"
SECRETS_PATH = REPO_ROOT / ".cursor" / ".mcp.secrets.json"
FIGMA_ENV_PATH = REPO_ROOT / ".cursor" / "figma.env.local"
FIGMA_ENV_EXAMPLE = REPO_ROOT / ".cursor" / "figma.env.example"


def _validate_token(token: str) -> tuple[bool, str]:
    req = urllib.request.Request(
        "https://api.figma.com/v1/me",
        headers={"X-Figma-Token": token, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:200]
        return False, f"HTTP {exc.code}: {body}"
    except urllib.error.URLError as exc:
        return False, str(exc.reason)
    email = data.get("email") or data.get("handle") or "ok"
    return True, str(email)


def _write_secrets(token: str) -> None:
    secrets: dict = {}
    if SECRETS_PATH.is_file():
        secrets = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    if not isinstance(secrets, dict):
        secrets = {}
    servers = secrets.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        servers = {}
        secrets["mcpServers"] = servers
    figma_srv = servers.setdefault("figma-read", {})
    if not isinstance(figma_srv, dict):
        figma_srv = {}
        servers["figma-read"] = figma_srv
    env = figma_srv.setdefault("env", {})
    if not isinstance(env, dict):
        env = {}
        figma_srv["env"] = env
    env["FIGMA_ACCESS_TOKEN"] = token
    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_PATH.write_text(json.dumps(secrets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_figma_env_local(token: str) -> None:
    FIGMA_ENV_PATH.write_text(
        "# Web Agent figma-read MCP（勿提交 git）\n"
        f"FIGMA_ACCESS_TOKEN={token}\n",
        encoding="utf-8",
    )


def _gateway_python() -> str:
    if GATEWAY_VENV_PY.is_file():
        return str(GATEWAY_VENV_PY)
    return sys.executable


def _run_mcp_check() -> int:
    gateway_dir = REPO_ROOT / "platform" / "dingtalk_gateway"
    snippet = """
import sys
sys.path.insert(0, %r)
from mcp_config import build_stdio_mcp_servers
loaded = build_stdio_mcp_servers()
if "figma-read" in loaded:
    print("[OK] figma-read 已加载，Web Agent 可使用 get_figma_node / get_figma_screenshot_url")
    raise SystemExit(0)
print("[FAIL] figma-read 未加载：请配置 FIGMA_ACCESS_TOKEN")
raise SystemExit(1)
""" % (
        str(gateway_dir),
    )
    import subprocess

    proc = subprocess.run([_gateway_python(), "-c", snippet], cwd=str(REPO_ROOT))
    return int(proc.returncode)


def _clear_mcp_cache() -> None:
    snippet = """
import sys
sys.path.insert(0, %r)
import mcp_config
mcp_config._cached_servers = None
mcp_config._cache_signature = None
""" % (
        str(REPO_ROOT / "platform" / "dingtalk_gateway"),
    )
    import subprocess

    subprocess.run([_gateway_python(), "-c", snippet], cwd=str(REPO_ROOT), check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="配置 figma-read MCP Token")
    parser.add_argument(
        "--token",
        help="Figma Personal Access Token（figd_…）；也可设环境变量 FIGMA_ACCESS_TOKEN",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="从 stdin 读取一行 token",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅检查当前配置是否可加载 figma-read",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="在浏览器打开 Figma Token 创建页",
    )
    args = parser.parse_args()

    if args.open:
        import webbrowser

        webbrowser.open("https://www.figma.com/settings/account#personal-access-tokens")
        print("已打开 Figma Personal access tokens 页面。")
        print("创建 Token 后执行：")
        print("  FIGMA_ACCESS_TOKEN=figd_xxx python3 platform/scripts/figma_read_setup.py")
        return 0

    if args.check:
        code = _run_mcp_check()
        if code != 0:
            print(f"  写入 {FIGMA_ENV_PATH} 或 {SECRETS_PATH}")
        return code

    token = (args.token or "").strip()
    if args.stdin:
        token = sys.stdin.read().strip()
    if not token:
        token = __import__("os").environ.get("FIGMA_ACCESS_TOKEN", "").strip()
    if not token:
        print("缺少 Token。创建方式：", file=sys.stderr)
        print("  python3 platform/scripts/figma_read_setup.py --open", file=sys.stderr)
        print("  FIGMA_ACCESS_TOKEN=figd_… python3 platform/scripts/figma_read_setup.py", file=sys.stderr)
        return 2

    ok, detail = _validate_token(token)
    if not ok:
        print(f"[FAIL] Token 校验失败: {detail}", file=sys.stderr)
        return 1

    _write_secrets(token)
    _write_figma_env_local(token)
    _clear_mcp_cache()
    print(f"[OK] 已写入 figma-read 凭证（Figma 账号: {detail}）")
    print(f"     {FIGMA_ENV_PATH}")
    print(f"     {SECRETS_PATH} (figma-read.env)")
    print("请重启 Web Agent：python3 platform/web_agent/restart.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
