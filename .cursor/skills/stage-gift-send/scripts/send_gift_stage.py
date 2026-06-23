#!/usr/bin/env python3
"""兼容路径：转发到 Gift/gift_execute.py。"""

import os
import subprocess
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
EXECUTE = os.path.join(REPO_ROOT, "Gift", "gift_execute.py")

if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, EXECUTE] + sys.argv[1:]))
