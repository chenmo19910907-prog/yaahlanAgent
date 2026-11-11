#!/usr/bin/env python3
"""拉取 voga-repos 服务端、Android/iOS 客户端与 yaahlan-fe H5 前端开发代码。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from devcode.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
