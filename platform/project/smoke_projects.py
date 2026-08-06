#!/usr/bin/env python3
"""多项目冒烟：依次跑 loader / second-project 单测。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PLATFORM = Path(__file__).resolve().parent
REPO = PLATFORM.parent


def _run(name: str, path: Path) -> int:
    print(f"\n=== {name} ===")
    proc = subprocess.run([sys.executable, str(path)], cwd=str(REPO), check=False)
    if proc.returncode != 0:
        print(f"[FAIL] {name}", file=sys.stderr)
    else:
        print(f"[OK] {name}")
    return proc.returncode


def main() -> int:
    tests = [
        ("verify_project_loader", PLATFORM / "verify_project_loader.py"),
        ("verify_second_project", PLATFORM / "verify_second_project.py"),
    ]
    failed = 0
    for name, path in tests:
        failed += _run(name, path) != 0
    if failed:
        print(f"\n{failed} suite(s) failed", file=sys.stderr)
        return 1
    print("\nAll project smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
