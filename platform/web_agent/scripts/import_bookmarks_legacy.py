#!/usr/bin/env python3
"""从 legacy localStorage JSON 文件合并进团队 bookmarks.json。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from bookmarks_store import load_bookmarks, merge_legacy_bookmarks, save_bookmarks  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="导入浏览器 localStorage 格式的快捷入口")
    parser.add_argument("legacy_json", type=Path, help="含 categories/items 的 JSON 文件")
    parser.add_argument("--dry-run", action="store_true", help="仅打印将导入的条目，不写盘")
    args = parser.parse_args()
    if not args.legacy_json.is_file():
        print(f"文件不存在: {args.legacy_json}", file=sys.stderr)
        return 1
    legacy = json.loads(args.legacy_json.read_text(encoding="utf-8"))
    merged, added = merge_legacy_bookmarks(load_bookmarks(), legacy)
    if not added:
        print("无新增条目（可能已全部存在或文件为空）")
        return 0
    print(f"将导入 {len(added)} 条：")
    for item in added:
        print(f"  - [{item['category']}] {item['label']} → {item['url']}")
    if args.dry_run:
        return 0
    save_bookmarks(merged)
    print("已写入 config/bookmarks.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
