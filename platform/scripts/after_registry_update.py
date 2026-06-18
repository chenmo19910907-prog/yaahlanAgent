#!/usr/bin/env python3
"""供各模块 generate_index 子进程调用，刷新 platform/catalog.html。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = Path(__file__).resolve().parent / "sync_registry_hook.py"


def main() -> int:
    if not HOOK.is_file():
        return 1
    return subprocess.call([sys.executable, str(HOOK), "--quiet"], cwd=str(REPO_ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
