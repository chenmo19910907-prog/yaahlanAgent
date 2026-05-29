#!/usr/bin/env python3
"""海外风控开放接口本地执行入口。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from risk.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
