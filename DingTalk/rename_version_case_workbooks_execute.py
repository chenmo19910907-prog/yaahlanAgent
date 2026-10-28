#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补全版本用例钉钉文档「（功能概况）」命名（实现见 scripts/dingtalk_rename_version_case_workbooks.py）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "dingtalk_rename_version_case_workbooks.py"

if __name__ == "__main__":
    os.execv(sys.executable, [sys.executable, str(_SCRIPT), *sys.argv[1:]])
