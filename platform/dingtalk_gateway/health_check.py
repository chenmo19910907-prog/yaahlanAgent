#!/usr/bin/env python3
"""网关健康检查：launchd / Bridge / MOA / 凭证。"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from env_loader import ENV_LOCAL, load_env_local, require_env
from moa_health import probe_moa_cookie

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parent.parent


def _check(name: str, ok: bool, detail: str) -> bool:
    mark = "OK" if ok else "FAIL"
    print(f"  [{mark}] {name}: {detail}")
    return ok


def main() -> int:
    load_env_local()
    ok_all = True
    print("=== 钉钉网关健康检查 ===")

    proc = subprocess.run(["pgrep", "-f", "dingtalk_gateway/server.py"], capture_output=True)
    server_running = proc.returncode == 0
    if not server_running:
        for _ in range(6):
            time.sleep(0.5)
            proc = subprocess.run(["pgrep", "-f", "dingtalk_gateway/server.py"], capture_output=True)
            if proc.returncode == 0:
                server_running = True
                break
    ok_all &= _check("server.py 进程", server_running, "运行中" if server_running else "未运行")

    try:
        require_env("CURSOR_API_KEY")
        ok_all &= _check("CURSOR_API_KEY", True, "已配置")
    except RuntimeError as exc:
        ok_all &= _check("CURSOR_API_KEY", False, str(exc))

    for name in ("DINGTALK_CLIENT_ID", "DINGTALK_CLIENT_SECRET"):
        try:
            require_env(name)
            ok_all &= _check(name, True, "已配置")
        except RuntimeError as exc:
            ok_all &= _check(name, False, str(exc))

    if server_running:
        ok_all &= _check("Cursor Bridge", True, "由 gateway 进程托管")
    else:
        ok_all &= _check("Cursor Bridge", False, "server 未运行，无法验证 Bridge")

    moa_env = REPO_ROOT / "MOA" / ".env.local"
    ok_all &= _check("MOA/.env.local", moa_env.is_file(), "存在" if moa_env.is_file() else "缺失")

    moa_ok, moa_detail = probe_moa_cookie()
    ok_all &= _check("MOA Cookie", moa_ok, moa_detail)

    ok_all &= _check(".env.local", ENV_LOCAL.is_file(), str(ENV_LOCAL))

    print()
    if ok_all:
        print("[PASS] 网关环境健康")
        return 0
    print("[WARN] 存在异常项，请按提示修复后 ./gateway_ctl.sh restart")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
