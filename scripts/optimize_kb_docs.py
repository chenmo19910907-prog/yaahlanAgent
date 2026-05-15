#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量优化 documents/documents 下的大模块知识库 Markdown：

- 统一换行（LF）、去除行尾空格
- 确保分隔线 '---' 与标题之间有合适空行
- 压缩连续空行（最多保留 2 个）
- 安全去重：仅当两个「## 功能模块：...」章节正文在规范化后完全一致时，删除重复章节

注意：不改动用例内容语义；不做智能合并/重写。
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


ROOT_DEFAULT = (
    Path(__file__).resolve().parent.parent / "documents" / "documents"
)


@dataclass
class Section:
    heading_line: str  # "## 功能模块：xxx"
    body: str  # content until next section or EOF


SECTION_RE = re.compile(r"(?m)^## 功能模块：.*$")


def normalize_text(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join([ln.rstrip() for ln in s.split("\n")])
    # 把连续空行压缩到最多 2 行，便于比较
    s = re.sub(r"\n{4,}", "\n\n\n", s)
    s = s.strip() + "\n"
    return s


def split_sections(text: str) -> Tuple[str, List[Section]]:
    """
    返回 (prefix, sections)。
    prefix：从文件头到第一个 '## 功能模块：' 之前的内容。
    """
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        return text, []

    prefix = text[: matches[0].start()]
    sections: List[Section] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end]
        lines = chunk.splitlines()
        heading_line = lines[0].rstrip()
        body = "\n".join(lines[1:]).lstrip("\n")
        sections.append(Section(heading_line=heading_line, body=body))
    return prefix, sections


def safe_dedupe_sections(sections: List[Section]) -> List[Section]:
    """
    去重策略：
    - 同一“模块名（原样 heading_line）”出现多次时，若后者 section 的规范化全文与先前某个完全一致，则删除后者。
    - 不尝试根据“同上”等做归并，避免误删。
    """
    seen: Dict[str, set[str]] = {}
    out: List[Section] = []
    for sec in sections:
        key = sec.heading_line
        full = normalize_text(sec.heading_line + "\n" + sec.body)
        if key not in seen:
            seen[key] = {full}
            out.append(sec)
            continue
        if full in seen[key]:
            # 完全重复，删除
            continue
        seen[key].add(full)
        out.append(sec)
    return out


def format_prefix(prefix: str) -> str:
    p = normalize_text(prefix)
    # 修复类似 '---## ' 的粘连
    p = p.replace("---##", "---\n\n##")
    return p


def format_sections(sections: List[Section]) -> str:
    parts: List[str] = []
    for sec in sections:
        heading = sec.heading_line.rstrip()
        body = normalize_text(sec.body).strip("\n")
        parts.append(f"{heading}\n\n{body}\n")
    # sections 之间保证空行
    return "\n".join([p.rstrip() for p in parts]).rstrip() + "\n"


def optimize_markdown(text: str) -> str:
    text = normalize_text(text)
    text = text.replace("---##", "---\n\n##")

    prefix, sections = split_sections(text)
    prefix = format_prefix(prefix)
    sections = safe_dedupe_sections(sections)
    sec_text = format_sections(sections) if sections else ""

    merged = (prefix.rstrip() + "\n\n" + sec_text.lstrip()).strip() + "\n"
    merged = re.sub(r"\n{4,}", "\n\n\n", merged)
    return merged


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root: Path = args.root
    if not root.is_dir():
        raise SystemExit(f"not a dir: {root}")

    files = sorted(root.glob("*.md"))
    changed = 0
    for p in files:
        old = p.read_text(encoding="utf-8")
        new = optimize_markdown(old)
        if new != old:
            changed += 1
            if not args.dry_run:
                p.write_text(new, encoding="utf-8")
    print(f"optimized {changed}/{len(files)} files in {root}")


if __name__ == "__main__":
    main()

