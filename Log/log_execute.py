#!/usr/bin/env python3
"""Yaahlan Kibana 日志查询本地入口。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from log.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
