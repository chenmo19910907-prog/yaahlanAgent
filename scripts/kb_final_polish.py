#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识库终稿抛光：补范围说明、去空「未归类需求」、目录说明去重。"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path
from typing import List, Tuple

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from project_paths import testcase_kb_root  # noqa: E402

ROOT_DEFAULT = testcase_kb_root()


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_reclass = _load_module("kb_reclassify_polish", "kb_reclassify.py")
INTROS = _reclass.INTROS
_kstyle = _load_module("kb_knowledge_style_polish", "kb_knowledge_style.py")
transform_toc = _kstyle.transform_toc

SCOPE_LINE_RE = re.compile(r"^> \*\*范围\*\*：.+$", re.M)
LEGACY_OTHER_PREFIX_RE = re.compile(r"^其他模块·+")
EMPTY_UNCAT_RE = re.compile(
    r"(?ms)^## 未归类需求\s*\n(?:\s*\n)*(?=## |\Z)"
)
# 无标题 ###，正文仅为目录式条目列表（优化残留）
JUNK_H3_RE = re.compile(
    r"(?ms)^###\s*\n+> \*\*版本\*\*[^\n]*\n+(?:- [^\n]+\n)+(?=\n### |\n## |\Z)"
)
KB_SCENARIO_IN_BLOCK_RE = re.compile(r"^\*\*[^*]+\*\*\s*$", re.M)


def apply_scope_intro(text: str, fname: str) -> Tuple[str, bool]:
    intro = INTROS.get(fname)
    if not intro:
        return text, False
    intro = intro.strip()
    if SCOPE_LINE_RE.search(text):
        return text, False
    lines = text.splitlines()
    if not lines or not lines[0].startswith("# "):
        return text, False
    out: List[str] = [lines[0], "", intro, ""]
    out.extend(lines[1:])
    return "\n".join(out), True


def remove_junk_empty_h3_blocks(text: str) -> Tuple[str, bool]:
    changed = False

    def _drop(m: re.Match[str]) -> str:
        nonlocal changed
        block = m.group(0)
        if KB_SCENARIO_IN_BLOCK_RE.search(block):
            return block
        changed = True
        return ""

    new = JUNK_H3_RE.sub(_drop, text)
    return new, changed


def remove_empty_uncategorized(text: str) -> Tuple[str, bool]:
    new = EMPTY_UNCAT_RE.sub("", text)
    # 未归类整节仅剩空白
    new = re.sub(
        r"(?ms)^## 未归类需求\s*\n(?:\s*\n)*(?=## |\Z)",
        "",
        new,
    )
    new = re.sub(r"\n{4,}", "\n\n\n", new)
    return new, new != text


def prune_toc_uncategorized(text: str) -> Tuple[str, bool]:
    if re.search(r"(?ms)^## 未归类需求\s*\n\s*###", text):
        return text, False
    new = re.sub(r"(?m)^- 未归类需求\s*\n", "", text)
    return new, new != text


def strip_legacy_other_prefix(text: str) -> Tuple[str, bool]:
    lines = text.splitlines()
    out: List[str] = []
    changed = False
    for line in lines:
        if line.startswith("## "):
            title = line[3:].strip()
            new_title = LEGACY_OTHER_PREFIX_RE.sub("", title)
            if new_title != title:
                changed = True
                out.append(f"## {new_title}")
                continue
        if line.startswith("- ") and not line.startswith("- ["):
            item = line[2:].strip()
            new_item = LEGACY_OTHER_PREFIX_RE.sub("", item)
            if new_item != item:
                changed = True
                out.append(f"- {new_item}")
                continue
        out.append(line)
    return "\n".join(out), changed


def dedupe_toc_intro(text: str) -> Tuple[str, bool]:
    first_sep = text.find("\n---\n")
    if first_sep == -1:
        return text, False
    body_rest = text[first_sep + 5 :]
    second_sep = body_rest.find("\n---\n")
    if second_sep == -1:
        return text, False
    prefix = text[: first_sep + 5]
    toc_block = body_rest[:second_sep]
    main = body_rest[second_sep + 5 :]
    new_toc = "\n".join(transform_toc(toc_block.splitlines()))
    merged = prefix + new_toc + "\n\n---\n\n" + main
    return merged, merged != text


def polish_file(path: Path) -> Tuple[bool, List[str]]:
    text = path.read_text(encoding="utf-8")
    notes: List[str] = []
    changed = False

    new, c = apply_scope_intro(text, path.name)
    if c:
        notes.append("scope")
        changed = True
    text = new

    new, c = remove_junk_empty_h3_blocks(text)
    if c:
        notes.append("junk-h3")
        changed = True
    text = new

    new, c = remove_empty_uncategorized(text)
    if c:
        notes.append("uncat")
        changed = True
    text = new

    new, c = prune_toc_uncategorized(text)
    if c:
        notes.append("toc-prune")
        changed = True
    text = new

    new, c = dedupe_toc_intro(text)
    if c:
        notes.append("toc")
        changed = True
    text = new

    new, c = strip_legacy_other_prefix(text)
    if c:
        notes.append("prefix")
        changed = True
    text = new

    if changed:
        path.write_text(text.strip() + "\n", encoding="utf-8")
    return changed, notes


def main() -> None:
    ap = argparse.ArgumentParser(description="知识库终稿抛光")
    ap.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root: Path = args.root
    n = 0
    for p in sorted(root.glob("*.md")):
        if p.name.lower() == "readme.md" or p.name.startswith("_"):
            continue
        if args.dry_run:
            old = p.read_text(encoding="utf-8")
            t = old
            t, _ = apply_scope_intro(t, p.name)
            t, _ = remove_junk_empty_h3_blocks(t)
            t, _ = remove_empty_uncategorized(t)
            t, _ = prune_toc_uncategorized(t)
            t, _ = dedupe_toc_intro(t)
            t, _ = strip_legacy_other_prefix(t)
            if t != old:
                n += 1
                print(f"[dry] {p.name}: would update")
            continue
        ch, notes = polish_file(p)
        if ch:
            n += 1
            print(f"{p.name}: {','.join(notes)}")
    print(f"kb-final-polish: {n} files updated")


if __name__ == "__main__":
    main()
