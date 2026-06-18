#!/usr/bin/env python3
"""E2E 自动化测试入口（独立于 adb/）。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from e2e.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
