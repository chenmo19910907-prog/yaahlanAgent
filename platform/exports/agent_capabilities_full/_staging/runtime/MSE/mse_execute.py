#!/usr/bin/env python3
"""MSE 服务配置本地执行入口。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mse.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
