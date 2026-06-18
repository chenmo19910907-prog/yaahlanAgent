#!/usr/bin/env python3
"""各模块 registry 更新后刷新 platform/catalog.html。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_catalog import refresh_catalog  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="registry 变更后同步工具平台 catalog.html")
    parser.add_argument("--quiet", action="store_true", help="成功时不打印 generated 行")
    args = parser.parse_args()
    return refresh_catalog(quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
