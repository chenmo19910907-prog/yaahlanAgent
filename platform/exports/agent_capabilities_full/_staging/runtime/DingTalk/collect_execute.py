#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钉钉目录链接列举 CLI 入口（实现见 scripts/dingtalk_collect_folder_links.py）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "dingtalk_collect_folder_links.py"

if __name__ == "__main__":
    os.execv(sys.executable, [sys.executable, str(_SCRIPT), *sys.argv[1:]])
