#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理知识库目录与 Sheet 标题：

- ## 目录 使用纯文本列表（`- 标题`），不含 Markdown 链接的 `(锚点)` 引用
- Sheet 标题移除 （…）、(…)、【…】 及负责人后缀
- 移除 Excel 默认工作表名（Sheet1、Sheet2、sheet3 等）及其正文章节
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path
from typing import List, Tuple

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent / "documents" / "documents"

SKIP_H2 = frozenset({"目录", "---", "知识地图（阶段）", "知识地图（阶段）"})

# Excel 默认工作表名：Sheet1、sheet2、Sheet3 …
DEFAULT_SHEET_RE = re.compile(r"(?i)sheet\d+")

# 全角/半角括号及其中的内容
PAREN_SEGMENT_RE = re.compile(r"[（(][^）)]*[）)]")
# 方括号标签（如 【实验】、【安安】）
BRACKET_SEGMENT_RE = re.compile(r"【[^】]*】")

# 标题末尾 -姓名（2～4 个汉字，常见负责人后缀）
PERSON_SUFFIX_RE = re.compile(r"[-－][\u4e00-\u9fff]{2,4}$")

# 标题末尾单独挂的人名（无括号）：如「优化需求-陈墨」已覆盖；-晓东 等
TRAILING_NAME_RE = re.compile(
    r"[-－](?:晓东|彦孝|振华|沈梦强|梦强|丁亮|陈墨|史磊|刘娜|一菲|宪华|阿龙|孙越)$"
)


def _load_content_opt():
    spec = importlib.util.spec_from_file_location(
        "content_opt", SCRIPTS / "content_optimize_kb_docs.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["content_opt"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_load_content_opt()  # 保持与 content_optimize_kb_docs 同环境（sheet_anchor 等）


def is_default_sheet_name(name: str) -> bool:
    return bool(DEFAULT_SHEET_RE.search((name or "").strip()))


def clean_sheet_title(title: str) -> str:
    """去掉括号/方括号引用与人名后缀，保留业务语义。"""
    s = title.strip()
    if not s or s in SKIP_H2:
        return s
    while True:
        prev = s
        s = PAREN_SEGMENT_RE.sub("", s)
        s = BRACKET_SEGMENT_RE.sub("", s)
        if s == prev:
            break
    s = PERSON_SUFFIX_RE.sub("", s)
    s = TRAILING_NAME_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"[-－·]{2,}", "·", s)
    s = s.strip(" -－·")
    return s or title.strip()


def extract_sheet_sections(lines: List[str]) -> List[Tuple[int, str]]:
    """(line_index, sheet_title) for ## sheet sections."""
    sections: List[Tuple[int, str]] = []
    for i, line in enumerate(lines):
        if not line.startswith("## "):
            continue
        title = line[3:].strip()
        if title in SKIP_H2 or title.startswith("知识地图"):
            continue
        sections.append((i, title))
    return sections


def rebuild_toc(sheet_titles: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for sn in sheet_titles:
        if sn in seen or is_default_sheet_name(sn):
            continue
        seen.add(sn)
        ordered.append(sn)
    toc = ["## 目录", ""]
    for sn in ordered:
        toc.append(f"- {sn}")
    toc.append("")
    return toc


TOC_LINK_RE = re.compile(r"^-\s+\[([^\]]+)\]\([^)]*\)\s*$")
TOC_PLAIN_RE = re.compile(r"^-\s+(.+?)\s*$")


def toc_line_from_title(title: str) -> str:
    return f"- {clean_sheet_title(title)}"


def is_stray_sheet_list_line(line: str) -> bool:
    s = line.strip()
    if not s.startswith("- "):
        return False
    m = TOC_LINK_RE.match(s)
    if m and is_default_sheet_name(m.group(1)):
        return True
    m2 = TOC_PLAIN_RE.match(s)
    return bool(m2 and is_default_sheet_name(m2.group(1)))


def clean_toc_link_line(line: str) -> Tuple[str, bool]:
    if is_stray_sheet_list_line(line):
        return "", True
    m = TOC_LINK_RE.match(line.strip())
    if m:
        new_line = toc_line_from_title(m.group(1))
        return new_line, new_line != line.strip()
    m2 = TOC_PLAIN_RE.match(line.strip())
    if m2:
        new_line = toc_line_from_title(m2.group(1))
        return new_line, new_line != line.strip()
    return line, False


def remove_default_sheet_sections(lines: List[str]) -> Tuple[List[str], int]:
    out: List[str] = []
    i = 0
    changes = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            title = line[3:].strip()
            if (
                title not in SKIP_H2
                and not title.startswith("知识地图")
                and is_default_sheet_name(title)
            ):
                i += 1
                while i < len(lines) and not lines[i].startswith("## "):
                    i += 1
                changes += 1
                continue
        out.append(line)
        i += 1
    return out, changes


STRUCTURE_LINE_OLD = (
    "- **结构**：`## Sheet` → `### 功能模块（可含多个 #### 子模块）` → 步骤/预期。"
)
STRUCTURE_LINE_NEW = "- **结构**：`## Sheet` → `### 功能模块` → `#### 子模块` → 步骤/预期。"


def process_file(text: str) -> Tuple[str, int]:
    lines = text.replace("\r\n", "\n").split("\n")
    changes = 0

    for i, line in enumerate(lines):
        if line == STRUCTURE_LINE_OLD:
            lines[i] = STRUCTURE_LINE_NEW
            changes += 1

    # 0) 删除误嵌入的 SheetN 目录行；删除 ## SheetN 整节
    kept: List[str] = []
    for line in lines:
        if is_stray_sheet_list_line(line):
            changes += 1
            continue
        kept.append(line)
    lines, n_sec = remove_default_sheet_sections(kept)
    changes += n_sec

    # 1) ## 目录 块内链接行
    toc_start = next(
        (i for i, line in enumerate(lines) if line.strip() == "## 目录"), None
    )
    toc_end = None
    if toc_start is not None:
        toc_end = toc_start + 1
        while toc_end < len(lines) and lines[toc_end].strip() != "---":
            toc_end += 1
        for i in range(toc_start + 1, toc_end):
            new_line, ch = clean_toc_link_line(lines[i])
            if ch:
                lines[i] = new_line
                changes += 1

    # 2) ## Sheet 标题
    sections = extract_sheet_sections(lines)
    new_titles: List[str] = []
    for idx, old_title in sections:
        new_title = clean_sheet_title(old_title)
        new_titles.append(new_title)
        if new_title != old_title:
            lines[idx] = f"## {new_title}"
            changes += 1

    # 3) 重建 ## 目录 块
    if toc_start is not None and new_titles and toc_end is not None:
        new_toc = rebuild_toc(new_titles)
        if lines[toc_start:toc_end] != new_toc:
            changes += 1
        lines[toc_start:toc_end] = new_toc

    return "\n".join(lines).strip() + "\n", changes


def main() -> None:
    ap = argparse.ArgumentParser(description="清理目录/Sheet 标题中的人名与括号")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root: Path = args.root

    total = 0
    files_changed = 0
    for p in sorted(root.glob("*.md")):
        if p.name.startswith("_") or p.name.lower() == "readme.md":
            continue
        old = p.read_text(encoding="utf-8")
        new, n = process_file(old)
        if n:
            files_changed += 1
            total += n
            print(f"  {p.name}: {n} 处")
            if not args.dry_run:
                p.write_text(new, encoding="utf-8")

    print(f"clean-toc-titles: {files_changed} 文件, 共 {total} 处变更")


if __name__ == "__main__":
    main()
