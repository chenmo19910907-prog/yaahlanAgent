#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钉钉用例表标 P0 绿色（实现见 scripts/dingtalk_excel_mark_p0.py）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "dingtalk_excel_mark_p0.py"
_VENV_PY = _ROOT / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel/venv/bin/python3"

if __name__ == "__main__":
    py = str(_VENV_PY) if _VENV_PY.is_file() else sys.executable
    os.execv(py, [py, str(_SCRIPT), *sys.argv[1:]])
