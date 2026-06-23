#!/usr/bin/env python3
"""Stage 测试环境 HTTP 送礼入口。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gift.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
