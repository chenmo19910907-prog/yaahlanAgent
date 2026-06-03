#!/usr/bin/env python3
"""从版本用例 xlsx 生成内网/外网测试总结 HTML 报告。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from report.generator import main

if __name__ == "__main__":
    raise SystemExit(main())
