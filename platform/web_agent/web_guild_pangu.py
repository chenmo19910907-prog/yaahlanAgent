"""Web Agent：盘古 shiftTime 配置表单 API（公会 / 币商）。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
IO_SCRIPT = REPO_ROOT / "workflow/scripts/guild_pangu_mse_io.py"
DEALER_SCENARIOS_REL = "workflow/config/dealer_pangu_shift_scenarios.json"
YAHA_SCENARIOS_REL = "workflow/config/yaha_pangu_scenarios.json"


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


def dealer_pangu_scenarios_payload() -> dict[str, Any]:
    return _run_io_script(["--scenarios-json", "--scenarios-file", DEALER_SCENARIOS_REL])


def dealer_pangu_current_payload(scenario_key: str | None = None) -> dict[str, Any]:
    key = str(scenario_key or "dealer_assistant_quota").strip() or "dealer_assistant_quota"
    return _run_io_script(
        ["--scenario", key, "--scenarios-file", DEALER_SCENARIOS_REL]
    )


def dealer_pangu_trade_union_fixed_hint() -> dict[str, Any]:
    return _run_io_script(["--trade-union-fixed-hint"])


def yaha_pangu_scenarios_payload() -> dict[str, Any]:
    return _run_io_script(["--scenarios-json", "--scenarios-file", YAHA_SCENARIOS_REL])


def yaha_pangu_current_payload(scenario_key: str | None = None) -> dict[str, Any]:
    key = str(scenario_key or "yaha_task_show_switch").strip() or "yaha_task_show_switch"
    return _run_io_script(
        ["--scenario", key, "--scenarios-file", YAHA_SCENARIOS_REL]
    )
