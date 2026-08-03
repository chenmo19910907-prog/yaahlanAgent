#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钉钉用例 → testcase-kb 同步 CLI 入口（实现见 scripts/dingtalk_kb_sync.py）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "dingtalk_kb_sync.py"

if __name__ == "__main__":
    os.execv(sys.executable, [sys.executable, str(_SCRIPT), *sys.argv[1:]])
