#!/usr/bin/env python3
"""Yaahlan Admin 后台接口本地执行入口。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from admin.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
