#!/usr/bin/env python3
"""Yaahlan 算薪专项自动化测试入口（pytest E2E · 工具平台登记）。"""

from __future__ import annotations

import os
import sys

_SALARY_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SALARY_DIR)

from salary.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
