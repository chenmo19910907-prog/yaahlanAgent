"""Web Agent：公会盘古配置表单 API（读场景清单与 MSE 当前值）。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
IO_SCRIPT = REPO_ROOT / "workflow/scripts/guild_pangu_mse_io.py"


def _run_io_script(args: list[str]) -> dict[str, Any]:
    cmd = [sys.executable, str(IO_SCRIPT), *args]
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit={proc.returncode}"
        raise RuntimeError(err)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"脚本输出非 JSON：{proc.stdout[:200]}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("脚本输出格式错误")
    return data


def guild_pangu_scenarios_payload() -> dict[str, Any]:
    return _run_io_script(["--scenarios-json"])


def guild_pangu_current_payload(scenario_key: str) -> dict[str, Any]:
    key = str(scenario_key or "").strip()
    if not key:
        raise ValueError("缺少 scenario")
    return _run_io_script(["--scenario", key])
