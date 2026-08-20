"""子进程执行模块 CLI，结构化返回 stdout/stderr。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from catalog import get_module, resolve_entry_argv

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _try_parse_json(text: str) -> Any | None:
    raw = (text or "").strip()
    if not raw or raw[0] not in "{[":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def run_argv(
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout_sec: int = 120,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not argv:
        raise ValueError("argv 不能为空")
    workdir = cwd or _REPO_ROOT
    try:
        proc = subprocess.run(
            argv,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return {
            "ok": False,
            "exit_code": -1,
            "error": f"执行超时（>{timeout_sec}s）",
            "stdout": stdout,
            "stderr": stderr,
            "argv": argv,
        }

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    data = _try_parse_json(stdout)
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "data": data,
        "argv": argv,
    }


def run_module_cli(
    module_id: str,
    args: list[str],
    *,
    timeout_sec: int = 120,
) -> dict[str, Any]:
    mod = get_module(module_id)
    if mod is None:
        raise ValueError(f"未找到模块: {module_id}")
    argv = resolve_entry_argv(mod.entry) + list(args or [])
    return run_argv(argv, timeout_sec=timeout_sec)
