#!/usr/bin/env python3
"""工作流录制与参数化复用入口。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workflow.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
