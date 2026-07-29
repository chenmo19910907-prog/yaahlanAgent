#!/usr/bin/env python3
"""Tunnel Mock 入口：整包 mock_cases / 字段 param_mock。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tunnel.mock_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
