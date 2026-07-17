"""Markdown 展示增强：列表缩进等。"""

from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^#{1,6}\s")
_LIST_ITEM_RE = re.compile(r"^(\s*)([-*+]|\d+\.)\s")


def enhance_markdown_list_indent(text: str) -> str:
    """标题后的同级列表项增加缩进，便于钉钉 / 移动端 Markdown 渲染层级。"""
    if not (text or "").strip():
        return text

    lines = text.splitlines()
    out: list[str] = []
    after_heading = False

    for line in lines:
        stripped = line.strip()
        if _HEADING_RE.match(stripped):
            after_heading = True
            out.append(line)
            continue

        match = _LIST_ITEM_RE.match(line)
        if match and after_heading and len(match.group(1)) < 2:
            out.append(f"  {line.lstrip()}")
            continue

        if stripped == "":
            after_heading = False
            out.append(line)
            continue

        if not match:
            after_heading = False
        out.append(line)

    return "\n".join(out)
