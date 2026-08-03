#!/usr/bin/env python3
"""MOA httpproxy 本地执行入口（兼容原有调用方式）。"""

from __future__ import annotations

import os
import sys

_MOA_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _MOA_DIR)

from moa.venv_bootstrap import ensure_moa_venv

ensure_moa_venv()

from moa.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
