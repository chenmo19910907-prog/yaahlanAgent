#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 testcase-kb 知识库移除「老版本 / 系统兼容」相关用例。
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent / "testcase-kb"
SCRIPTS = Path(__file__).resolve().parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


content_opt = _load("content_opt", SCRIPTS / "content_optimize_kb_docs.py")
csm = _load("content_split", SCRIPTS / "content_split_merge_kb.py")
kb_split = _load("kb_split", SCRIPTS / "kb_split_submodules.py")

CaseBlock = content_opt.CaseBlock
normalize_lines = content_opt.normalize_lines

STEP_RE = re.compile(r"^- \*\*步骤\*\*：(.+)$")
EXPECT_RE = re.compile(r"^  - \*\*预期\*\*：(.+)$")

SHEET_DROP_RE = re.compile(
    r"Android回退|回退\s*SDK|新老版本兼容|版本兼容|系统兼容测试",
    re.I,
)

MODULE_DROP_RE = re.compile(
    r"老版本|旧版本|低版本|"
    r"新老版本|新旧版本|"
    r"系统兼容|版本兼容|兼容性|"
    r"Android回退|回退\s*SDK|"
    r"历史功能回测|功能回测|"
    r"及之前旧版本",
    re.I,
)

SOURCE_DROP_RE = re.compile(r"Android回退|回退SDK", re.I)

# 步骤/预期中含以下任一即删除（整段步骤或单行预期）
STEP_DROP_RE = re.compile(
    r"老版本|旧版本|低版本|"
    r"新旧版本|新老版本|"
    r"系统兼容|版本兼容|"
    r"Android回退|回退SDK|"
    r"未升级|历史功能回测|线上功能回测|"
    r"版本判断|做版本判断",
    re.I,
)

EXPECT_DROP_RE = re.compile(
    r"老版本|旧版本|老样式|低版本|"
    r"新旧版本|新老版本|"
    r"旧链接|旧家族|未升级|请升级最新版本",
    re.I,
)


def _step_text(line: str) -> str:
    m = STEP_RE.match(line.strip())
    return m.group(1).strip() if m else ""


def _expect_text(line: str) -> str:
    m = EXPECT_RE.match(line)
    return m.group(1).strip() if m else ""


def should_drop_block(b: CaseBlock) -> bool:
    if SHEET_DROP_RE.search(b.sheet or ""):
        return True
    if SOURCE_DROP_RE.search(b.source_file or ""):
        return True
    for name in (b.module, b.parent_module):
        n = (name or "").strip()
        if n and MODULE_DROP_RE.search(n):
            return True
    return False


def filter_body(body: str) -> str:
    lines = body.splitlines()
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if STEP_RE.match(line):
            if STEP_DROP_RE.search(_step_text(line)):
                i += 1
                while i < len(lines) and not STEP_RE.match(lines[i]):
                    i += 1
                continue
            out.append(line)
            i += 1
            continue
        if EXPECT_RE.match(line):
            if EXPECT_DROP_RE.search(_expect_text(line)):
                i += 1
                continue
            out.append(line)
            i += 1
            continue
        out.append(line)
        i += 1
    return normalize_lines("\n".join(out))


def filter_block(b: CaseBlock) -> CaseBlock | None:
    if should_drop_block(b):
        return None
    new_body = filter_body(b.body)
    if not new_body or not re.search(r"\*\*步骤\*\*", new_body):
        return None
    return CaseBlock(
        sheet=b.sheet,
        module=b.module,
        version_label=b.version_label,
        version_tuple=b.version_tuple,
        source_file=b.source_file,
        body=new_body,
        parent_module=b.parent_module,
    )


def write_all(root: Path, trees: dict) -> None:
    written: List[str] = []
    for fk, sheets_map in trees.items():
        title = fk.replace(".md", "")
        md = csm.build_from_tree(title, sheets_map)
        if fk == "房间PK.md" and md.startswith(f"# {title}"):
            rest = md.split("\n---\n\n", 1)
            body = rest[-1] if len(rest) > 1 else md
            if body.lstrip().startswith(f"# {title}"):
                body = body.split("\n", 1)[1]
            md = (
                "# 房间PK\n\n> **说明**：已移除老版本/系统兼容专项用例。\n\n---\n\n"
                + body.lstrip("\n")
            )
        (root / fk).write_text(md, encoding="utf-8")
        written.append(fk)

    keep = set(written) | {"README.md"}
    for p in root.glob("*.md"):
        if p.name not in keep and not p.name.startswith("_"):
            p.unlink()


def main() -> None:
    ap = argparse.ArgumentParser(description="移除老版本/系统兼容用例")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root: Path = args.root

    removed = 0
    kept: List[CaseBlock] = []
    for b in kb_split.load_blocks(root):
        nb = filter_block(b)
        if nb is None:
            removed += 1
        else:
            kept.append(nb)

    latest = kb_split.pick_latest(kept)
    trees = kb_split.build_trees(latest)
    print(f"过滤: 删除 {removed} 块, 保留 {len(latest)} 键, 输出 {len(trees)} 个文件")

    if args.dry_run:
        return

    write_all(root, trees)

    opt = SCRIPTS / "optimize_kb_docs.py"
    if opt.exists():
        subprocess.run(
            [sys.executable, str(opt), "--root", str(root)],
            check=False,
        )

    pat = re.compile(r"老版本|旧版本|系统兼容|Android回退|回退SDK|新老版本|版本兼容")
    left = 0
    for p in root.glob("*.md"):
        if p.name.startswith("_") or p.name == "README.md":
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if "来源版本" in line:
                continue
            if pat.search(line):
                left += 1
    print(f"version_compat_filter done (残留非元数据行约 {left} 处)")


if __name__ == "__main__":
    main()
