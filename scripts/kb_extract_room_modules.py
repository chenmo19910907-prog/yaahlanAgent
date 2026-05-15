#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 房间.md 拆出独立子模块（仅红包、成员），其余仍保留在 房间.md。

  房间红包.md  — 红包/宝箱相关
  房间成员.md  — 成员与等级、管理员、门槛等
  房间.md      — 其它房间用例

用法：python3 scripts/kb_extract_room_modules.py
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent / "documents" / "documents"
SCRIPTS = Path(__file__).resolve().parent

EXTRACT_SUB_TO_FILE = {
    "红包": "房间红包.md",
    "成员管理": "房间成员.md",
}

ROOM_SOURCE = "房间.md"

# 仅强相关才从 房间.md 拆出切片
RED_PACKET_PATH_SEG = "红包与宝箱"
RED_PACKET_LEAF_STRONG_RE = re.compile(
    r"^房间红包|^发红包|抢红包|红包雨|宝箱|红包与宝箱",
    re.I,
)
RED_PACKET_SHEET_WEAK_RE = re.compile(
    r"财富等级|VIP\d|礼物展馆|心愿礼物|麦位样式|优化需求$|未归类|&",
    re.I,
)

MEMBER_PATH_SEG = "成员与等级"
MEMBER_LEAF_STRONG_RE = re.compile(
    r"成员与等级|房间成员|管理员|移除成员|成员门槛|成员列表|封禁列表",
    re.I,
)
MEMBER_SHEET_WEAK_RE = re.compile(
    r"财富等级改版|标签UI|隐身设置|贵族$|优化需求$|&",
    re.I,
)


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
extract_blocks = content_opt.extract_blocks
classify_sub = kb_split.classify_sub
norm_module_key = kb_split.norm_module_key


def _sheet_leaf(sheet: str) -> str:
    parts = [p.strip() for p in (sheet or "").split("·") if p.strip()]
    return parts[-1] if parts else ""


def _should_extract_red_packet(sheet: str) -> bool:
    sn = (sheet or "").strip()
    if not sn or RED_PACKET_SHEET_WEAK_RE.search(sn) or "&" in sn:
        return False
    if RED_PACKET_PATH_SEG in sn.split("·"):
        return True
    leaf = _sheet_leaf(sn)
    return bool(RED_PACKET_LEAF_STRONG_RE.search(leaf))


def _should_extract_member(sheet: str) -> bool:
    sn = (sheet or "").strip()
    if not sn or MEMBER_SHEET_WEAK_RE.search(sn) or "&" in sn:
        return False
    if MEMBER_PATH_SEG in sn.split("·"):
        return True
    leaf = _sheet_leaf(sn)
    return bool(MEMBER_LEAF_STRONG_RE.search(leaf))


def route_file(sheet: str, module: str, body: str) -> str:
    sub = classify_sub("room", sheet, module, body)
    if sub == "红包" and _should_extract_red_packet(sheet):
        return EXTRACT_SUB_TO_FILE["红包"]
    if sub == "成员管理" and _should_extract_member(sheet):
        return EXTRACT_SUB_TO_FILE["成员管理"]
    return ROOM_SOURCE


def pick_latest(
    blocks: List[CaseBlock],
) -> Dict[Tuple[str, str, str], CaseBlock]:
    best: Dict[Tuple[str, str, str], CaseBlock] = {}
    for b in blocks:
        sheet = b.sheet or "未归类需求"
        if csm.is_default_sheet_name(sheet):
            continue
        fname = route_file(sheet, b.module or "", b.body)
        key = (fname, sheet, norm_module_key(b.module))
        if key not in best or b.version_tuple > best[key].version_tuple:
            best[key] = b
    return best


def build_trees(
    latest: Dict[Tuple[str, str, str], CaseBlock],
) -> Dict[str, Dict[str, Dict[str, List[CaseBlock]]]]:
    trees: Dict[str, Dict[str, Dict[str, List[CaseBlock]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for (fname, sheet, _mk), b in latest.items():
        cluster = csm.merge_cluster_key(sheet, b.module)
        bucket = trees[fname][sheet][cluster]
        if not any(x.module == b.module for x in bucket):
            bucket.append(b)
    return trees


def main() -> None:
    ap = argparse.ArgumentParser(description="从房间.md拆出红包/成员独立文件")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root: Path = args.root

    src = root / ROOM_SOURCE
    if not src.exists():
        raise SystemExit(f"未找到 {ROOM_SOURCE}")

    blocks = extract_blocks(src.read_text(encoding="utf-8"))
    if not blocks:
        raise SystemExit("房间.md 无可用用例块")

    latest = pick_latest(blocks)
    trees = build_trees(latest)

    for fk in sorted(trees.keys()):
        n = sum(len(c) for c in trees[fk].values())
        print(f"  {fk}: {n} 模块, {len(trees[fk])} sheets")

    if args.dry_run:
        return

    for fk, sheets_map in sorted(trees.items()):
        title = fk.replace(".md", "")
        (root / fk).write_text(
            csm.build_from_tree(title, sheets_map),
            encoding="utf-8",
        )

    subprocess.run(
        [sys.executable, str(SCRIPTS / "kb_clean_toc_titles.py"), "--root", str(root)],
        check=False,
    )
    print(f"extract-room-modules done -> {root}")


if __name__ == "__main__":
    main()
