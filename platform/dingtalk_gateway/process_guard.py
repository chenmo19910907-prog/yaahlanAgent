"""启动前检查：禁止重复 Stream 连接。"""

from __future__ import annotations

import os
import subprocess
import sys

_CONFLICT_PATTERNS = (
    "dingtalk_gateway/server.py",
    "dingtalk_gateway/bot_echo.py",
    "dingtalk_gateway/start_gateway.sh",
)


def ensure_single_gateway_process(*, allow_same_pid: bool = True) -> None:
    """若已有其它网关 Stream 进程则退出。"""
    my_pid = os.getpid()
    conflicts: list[str] = []
    for pattern in _CONFLICT_PATTERNS:
        proc = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
        if proc.returncode != 0:
            continue
        for token in proc.stdout.strip().split():
            if not token.isdigit():
                continue
            pid = int(token)
            if allow_same_pid and pid == my_pid:
                continue
            if pid != my_pid:
                conflicts.append(f"{pattern} (pid={pid})")
    if conflicts:
        detail = "; ".join(dict.fromkeys(conflicts))
        print(
            f"[FAIL] 检测到已有 Stream 网关进程，同一时间只能一个连接：{detail}",
            file=sys.stderr,
        )
        raise SystemExit(1)
