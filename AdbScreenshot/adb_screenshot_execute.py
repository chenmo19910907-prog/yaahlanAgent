#!/usr/bin/env python3
"""无线 ADB 整屏截图入口。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adb.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
