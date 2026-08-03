#!/usr/bin/env python3
"""Tunnel 抓包平台本地查询入口。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tunnel.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
