"""Web Agent：代码×用例交叉审查表单 API（读五阶段工作流清单）。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
IO_SCRIPT = REPO_ROOT / "DevCode/scripts/code_testcase_review_panel_io.py"


def code_testcase_review_scenarios_payload() -> dict[str, Any]:
    cmd = [sys.executable, str(IO_SCRIPT), "--scenarios-json"]
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
