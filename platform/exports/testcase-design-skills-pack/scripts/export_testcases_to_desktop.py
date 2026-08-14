#!/usr/bin/env python3
"""将 temporary_testcase 下的用例导出到桌面或指定目录。"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from project_paths import temporary_testcase_dir  # noqa: E402

DEFAULT_SRC = temporary_testcase_dir()


def main() -> int:
    parser = argparse.ArgumentParser(description="导出 temporary_testcase 用例副本")
    parser.add_argument(
        "--src",
        type=Path,
        default=DEFAULT_SRC,
        help="源目录",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="输出目录；默认 ~/Desktop/yaahlan_testcases_<时间戳>",
    )
    parser.add_argument(
        "--include-json",
        action="store_true",
        help="同时复制 .json",
    )
    args = parser.parse_args()

    src = args.src.expanduser()
    if not src.is_dir():
        print(f"源目录不存在: {src}", file=sys.stderr)
        return 1

    patterns = ["*.md"] if not args.include_json else ["*.md", "*.json"]
    files: list[Path] = []
    for pat in patterns:
        files.extend(src.glob(pat))
    files = sorted(set(files))
    if not files:
        print(f"源目录无 .md 文件: {src}", file=sys.stderr)
        return 1

    if args.out_dir:
        out = args.out_dir.expanduser()
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = Path.home() / "Desktop" / f"yaahlan_testcases_{stamp}"

    out.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, out / f.name)

    print(f"已导出 {len(files)} 个文件 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
