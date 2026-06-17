#!/usr/bin/env python3
"""线上环境（Admin / MOA / Tunnel）统一执行入口。"""

import os
import sys

_ONLINE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ONLINE_DIR)

from cli import main

if __name__ == "__main__":
    raise SystemExit(main())
