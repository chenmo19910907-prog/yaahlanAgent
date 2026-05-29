#!/usr/bin/env python3
"""MOA httpproxy 本地执行入口（兼容原有调用方式）。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from moa.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
