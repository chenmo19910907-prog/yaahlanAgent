#!/usr/bin/env python3
"""根据模块名/PRD 关键词推荐应阅读的知识库与模板路径。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kb_index import KbHit, match_module_keys, resolve_hits

ROOT = Path(__file__).resolve().parent.parent

KIND_LABEL = {
    "documents": "documents",
    "testcase_kb": "testcase-kb",
    "bug_kb": "bug-kb",
    "online_kb": "online-kb",
    "templates": "templates",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="根据模块关键词推荐知识库文件（生成用例前阅读）"
    )
    parser.add_argument(
        "query",
        nargs="*",
        help='模块关键词，如: 礼物 榜单 动态；或 --file modules.txt',
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="每行一个模块/关键词的文本文件",
    )
    args = parser.parse_args()

    texts: list[str] = list(args.query)
    if args.file:
        path = args.file.expanduser()
        if not path.is_file():
            print(f"找不到文件: {path}", file=sys.stderr)
            return 1
        texts.extend(
            ln.strip()
            for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        )
    if not texts:
        parser.print_help()
        return 1

    keys: list[str] = []
    for text in texts:
        keys.extend(match_module_keys(text))
    keys = list(dict.fromkeys(keys))
    if not keys:
        print("未匹配到模块，请换关键词或查阅 rules/version_testcase_generation_rules.md §1.2")
        return 1

    hits = resolve_hits(keys)
    print(f"匹配模块键: {', '.join(keys)}\n")
    by_kind: dict[str, list[KbHit]] = {}
    for hit in hits:
        by_kind.setdefault(hit.kind, []).append(hit)

    order = (
        "documents",
        "testcase_kb",
        "bug_kb",
        "online_kb",
        "templates",
    )
    for kind in order:
        group = by_kind.get(kind)
        if not group:
            continue
        print(f"## {KIND_LABEL.get(kind, kind)}")
        for hit in group:
            try:
                rel = hit.path.relative_to(ROOT)
            except ValueError:
                rel = hit.path
            print(f"  - {rel}  ({hit.note})")
        print()

    print("建议阅读顺序: documents → testcase-kb → bug-kb/online-kb → templates")
    return 0


if __name__ == "__main__":
    # 脚本目录即 sys.path[0]，可直接 import kb_index
    raise SystemExit(main())
