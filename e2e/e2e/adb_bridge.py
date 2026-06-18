"""E2E 读屏桥接：仅允许 observe / locate / activity / devices 原子命令（禁止 macro）。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

from .paths import repo_root

_ALLOWED_COMMANDS = frozenset({"observe", "locate", "activity", "devices"})


def adb_execute(args: list[str], *, timeout_s: float = 120.0) -> tuple[int, str, str]:
    if not args:
        raise ValueError("adb 参数为空")
    if args[0] not in _ALLOWED_COMMANDS:
        raise RuntimeError(
            f"e2e 禁止 adb 子命令 {args[0]!r}；请用 e2e flow（launch/tap/text）或 perceive 层"
        )

    entry = repo_root() / "adb" / "adb_execute.py"
    if not entry.is_file():
        raise FileNotFoundError(f"缺少 adb 读屏入口: {entry}")

    env = os.environ.copy()
    serial = env.get("E2E_DEVICE_SERIAL", "").strip()
    cmd = [sys.executable, str(entry), *args]
    if serial and "-s" not in args and "--serial" not in args:
        cmd = [sys.executable, str(entry), "-s", serial, *args]

    proc = subprocess.run(
        cmd,
        cwd=str(repo_root()),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def adb_execute_act(args: list[str], *, timeout_s: float = 120.0) -> tuple[int, str, str]:
    """执行层 tap/text/key：走 adb_execute 原子命令（非 macro）。"""
    allowed = {"tap", "text", "key", "locate", "capture"}
    if not args or args[0] not in allowed:
        raise RuntimeError(f"adb_execute_act 不支持: {args[:1]}")

    entry = repo_root() / "adb" / "adb_execute.py"
    serial = os.environ.get("E2E_DEVICE_SERIAL", "").strip()
    cmd = [sys.executable, str(entry), *args]
    if serial:
        cmd = [sys.executable, str(entry), "-s", serial, *args]

    proc = subprocess.run(
        cmd,
        cwd=str(repo_root()),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def parse_json_stdout(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        raise ValueError("adb 无 JSON 输出")
    start = text.find("{")
    if start < 0:
        raise ValueError(f"adb 输出非 JSON: {text[:200]}")
    data = json.loads(text[start:])
    if not isinstance(data, dict):
        raise ValueError("adb JSON 须为 object")
    return data
