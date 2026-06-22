#!/usr/bin/env python3
"""根据模块名/PRD 关键词推荐应阅读的知识库与模板路径。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kb_index import (
    DIR_KIND,
    KbHit,
    iter_template_markdown,
    match_module_keys,
    resolve_hits,
    score_template_relevance,
)

ROOT = Path(__file__).resolve().parent.parent

KIND_LABEL = {
    "documents": "documents",
    "testcase_kb": "testcase-kb",
    "bug_kb": "bug-kb",
    "templates": "templates",
}


def _annotate_template_hits(hits: list[KbHit], queries: list[str]) -> list[KbHit]:
    scored: list[tuple[int, KbHit]] = []
    for hit in hits:
        if hit.kind != "templates":
            scored.append((0, hit))
            continue
        score = score_template_relevance(hit.path, queries)
        if score > 0:
            note = f"推荐（匹配度 {score}）"
        else:
            note = hit.note or "历史活动参考"
        scored.append((score, KbHit(kind=hit.kind, path=hit.path, note=note)))
    scored.sort(key=lambda item: (-item[0], str(item[1].path)))
    return [hit for _, hit in scored]


def _append_all_templates(hits: list[KbHit]) -> list[KbHit]:
    seen = {str(hit.path) for hit in hits}
    out = list(hits)
    templates_root = DIR_KIND["templates"]
    for path in iter_template_markdown():
        tag = str(path)
        if tag in seen:
            continue
        seen.add(tag)
        try:
            rel = path.relative_to(templates_root)
        except ValueError:
            rel = path
        note = "通用模块模板" if len(rel.parts) == 1 else "历史活动参考"
        out.append(KbHit(kind="templates", path=path, note=note))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="根据模块关键词推荐知识库文件（生成用例前阅读）"
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="模块关键词，如: 礼物 榜单 世界杯；或 --file modules.txt",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="每行一个模块/关键词的文本文件",
    )
    parser.add_argument(
        "--activity",
        action="store_true",
        help="活动用例模式：收录 templates/ 下全部 .md（含子目录）",
    )
    parser.add_argument(
        "--all-templates",
        action="store_true",
        help="无论匹配何种模块，均列出 templates/ 下全部 .md",
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

    rank_texts = list(texts)

    if args.activity and "活动" not in texts:
        texts.append("活动")

    if not texts and not args.all_templates:
        parser.print_help()
        return 1

    keys: list[str] = []
    for text in texts:
        keys.extend(match_module_keys(text))
    if args.activity and "activity" not in keys:
        keys.append("activity")
    keys = list(dict.fromkeys(keys))

    if not keys and not args.all_templates:
        print("未匹配到模块，请换关键词或查阅 rules/version_testcase_generation_rules.md §1.2")
        return 1

    hits = resolve_hits(keys) if keys else []
    if args.all_templates:
        hits = _append_all_templates(hits)

    hits = _annotate_template_hits(hits, rank_texts)

    if keys:
        print(f"匹配模块键: {', '.join(keys)}")
    if args.activity or args.all_templates:
        template_count = sum(1 for hit in hits if hit.kind == "templates")
        print(f"活动模板索引: templates/**/*.md 共 {template_count} 个")
    print()

    by_kind: dict[str, list[KbHit]] = {}
    for hit in hits:
        by_kind.setdefault(hit.kind, []).append(hit)

    order = (
        "documents",
        "testcase_kb",
        "bug_kb",
        "templates",
    )
    for kind in order:
        group = by_kind.get(kind)
        if not group:
            continue
        print(f"## {KIND_LABEL.get(kind, kind)}")
        if kind == "templates" and len(group) > 10:
            recommended = [hit for hit in group if hit.note.startswith("推荐")]
            if recommended:
                print("  （优先阅读「推荐」；其余按相似活动结构对齐参考）")
        for hit in group:
            try:
                rel = hit.path.relative_to(ROOT)
            except ValueError:
                rel = hit.path
            print(f"  - {rel}  ({hit.note})")
        print()

    if args.activity or args.all_templates:
        print(
            "活动用例阅读建议: testcase-kb/活动.md → bug-kb/活动.md → "
            "templates 推荐项 → 根目录通用模板（抽奖/榜单等）→ 其余历史活动"
        )
    else:
        print("建议阅读顺序: documents → testcase-kb → bug-kb → templates")
    return 0


if __name__ == "__main__":
    # 脚本目录即 sys.path[0]，可直接 import kb_index
    raise SystemExit(main())
