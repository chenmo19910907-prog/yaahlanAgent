#!/usr/bin/env python3
"""导出工具平台离线版到桌面（提示语按钮为「复制」）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PLATFORM_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = PLATFORM_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_catalog import _load_catalog_data, _render_html  # noqa: E402

DEFAULT_NAME = "Yaahlan智能工具平台.html"


def main() -> int:
    parser = argparse.ArgumentParser(description="导出工具平台离线版到桌面")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=f"输出路径（默认 ~/Desktop/{DEFAULT_NAME}）",
    )
    args = parser.parse_args()

    out_path = args.output or (Path.home() / "Desktop" / DEFAULT_NAME)
    data = _load_catalog_data()
    out_path.write_text(_render_html(data, export_mode=True), encoding="utf-8")
    print(f"exported: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
