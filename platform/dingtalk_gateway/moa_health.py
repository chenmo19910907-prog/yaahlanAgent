"""MOA 测试环境 Cookie 探活。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parent.parent

PROBE_USER_ID = "100000001"


def probe_moa_cookie(*, timeout_s: int = 30) -> tuple[bool, str]:
    """返回 (是否可用, 说明)。"""
    cmd = [
        sys.executable,
        str(REPO_ROOT / "MOA" / "moa_execute.py"),
        "--payload-file",
        str(REPO_ROOT / "MOA" / "templates" / "VIP-增加经验值.json"),
        "--vip-user-id",
        PROBE_USER_ID,
        "--vip-query-current",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return False, "MOA 探活超时"

    output = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    if "Aegis SSO" in output or "<!doctype html>" in output.lower():
        return False, "MOA Cookie 已过期，请登录 https://mse.wemomo.com 后更新 MOA/.env.local"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:300]
        return False, detail or f"MOA 探活失败 exit={proc.returncode}"
    return True, "MOA 测试环境可用"
