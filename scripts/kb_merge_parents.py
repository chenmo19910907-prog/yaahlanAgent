#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将同父类型的知识库 md 合并为单文件：

  房间麦位.md + 房间进房.md + … → 房间.md
  礼物*.md → 礼物.md
  …

保留独立文件：房间PK、神秘人/VIP/贵族/财富等级、以及未参与合并的其它父模块。
房间/礼物子文件回并时不再叠「子域·」前缀（Sheet 名已含业务语义）。

仅合并房间+礼物：python3 scripts/kb_merge_parents.py --parents room,gift
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent / "testcase-kb"
SCRIPTS = Path(__file__).resolve().parent

# 文件名前缀 -> (parent_key, 合并后文件名)
MERGE_PREFIXES: List[Tuple[str, str, str]] = [
    ("房间", "room", "房间.md"),  # 不含 房间PK
    ("礼物", "gift", "礼物.md"),
    ("消息", "message", "消息.md"),
    ("币商", "coin", "币商.md"),
    ("家族", "family", "家族.md"),
    ("主题房", "theme_room", "主题房.md"),
    ("动态", "moments", "动态.md"),
]

# 从 房间.md 拆出的子模块，回并时不再并入 房间.md
ROOM_SLICE_FILES = frozenset({"房间红包.md", "房间成员.md"})

STANDALONE_FILES = frozenset(
    {
        "房间PK.md",
        *ROOM_SLICE_FILES,
        "游戏.md",
        "公会.md",
        "榜单.md",
        "活动.md",
        "注册登录.md",
        "人脸认证.md",
        "客服.md",
        "超管.md",
    }
)

# 独立功能库与其它父模块：合并房间/礼物时绝不删除
PRESERVE_ALWAYS = frozenset(
    {
        "神秘人.md",
        "特权VIP.md",
        "贵族.md",
        "财富等级.md",
        "消息.md",
        "币商.md",
        "家族.md",
        "主题房.md",
        "动态.md",
        "客服.md",
        "超管.md",
        "游戏.md",
        "公会.md",
        "榜单.md",
        "活动.md",
        "注册登录.md",
        "人脸认证.md",
        "房间PK.md",
        "房间红包.md",
        "房间成员.md",
        "README.md",
    }
)

PARENT_MERGE_OUT: Dict[str, str] = {
    "room": "房间.md",
    "gift": "礼物.md",
    "message": "消息.md",
    "coin": "币商.md",
    "family": "家族.md",
    "theme_room": "主题房.md",
    "moments": "动态.md",
    "customer_service": "客服.md",
    "super_admin": "超管.md",
}


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


def infer_merge_target(filename: str) -> Tuple[Optional[str], str]:
    """
    返回 (合并目标 md 名, 子域标签)。
    standalone 返回 (文件名, "")。
  """
    if filename in STANDALONE_FILES:
        return filename, ""
    if filename.startswith("房间PK"):
        return "房间PK.md", ""

    for prefix, _pk, out_name in MERGE_PREFIXES:
        if prefix == "房间" and filename in ("房间PK.md", *ROOM_SLICE_FILES):
            continue
        if filename.startswith(prefix) and filename.endswith(".md"):
            sub = filename[: -len(".md")][len(prefix) :]
            return out_name, sub or "综合"
    return None, ""


def load_tagged_blocks(root: Path) -> List[Tuple[CaseBlock, str, str]]:
    """(block, target_file, sub_domain)"""
    out: List[Tuple[CaseBlock, str, str]] = []
    for p in sorted(root.glob("*.md")):
        if p.name.startswith("_") or p.name.lower() == "readme.md":
            continue
        target, sub = infer_merge_target(p.name)
        if not target:
            continue
        for b in extract_blocks(p.read_text(encoding="utf-8")):
            out.append((b, target, sub))
    return out


def sheet_with_sub(sub: str, sheet: str, *, add_sub_prefix: bool) -> str:
    sn = (sheet or "未归类需求").strip()
    if not add_sub_prefix or not sub or sub == "综合":
        return sn
    if sn.startswith(f"{sub}·"):
        return sn
    return f"{sub}·{sn}"


def pick_latest(
    tagged: List[Tuple[CaseBlock, str, str]],
    *,
    add_sub_prefix: bool,
) -> Dict[Tuple[str, str, str], CaseBlock]:
    best: Dict[Tuple[str, str, str], CaseBlock] = {}
    for b, target, sub in tagged:
        sheet = sheet_with_sub(sub, b.sheet or "", add_sub_prefix=add_sub_prefix)
        key = (target, sheet, kb_split.norm_module_key(b.module))
        if key not in best or b.version_tuple > best[key].version_tuple:
            nb = CaseBlock(
                sheet=sheet,
                module=b.module,
                version_label=b.version_label,
                version_tuple=b.version_tuple,
                source_file=b.source_file,
                body=b.body,
                parent_module=b.parent_module,
            )
            best[key] = nb
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


def source_files_for_parents(root: Path, parents: Set[str]) -> List[Path]:
    """收集待合并的源文件路径。"""
    prefix_by_parent = {v: k for k, v in PARENT_MERGE_OUT.items()}
    out: List[Path] = []
    for p in sorted(root.glob("*.md")):
        if p.name.startswith("_") or p.name.lower() == "readme.md":
            continue
        target, _sub = infer_merge_target(p.name)
        if not target:
            continue
        parent_key = prefix_by_parent.get(target)
        if parent_key and parent_key in parents:
            out.append(p)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="按父类型合并知识库 md")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument(
        "--parents",
        type=str,
        default="all",
        help="要合并的父域：room,gift,... 或 all",
    )
    ap.add_argument(
        "--sub-prefix",
        action="store_true",
        help="合并时为 Sheet 加「子域·」前缀（默认不加）",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root: Path = args.root

    if args.parents.strip().lower() == "all":
        parents_scope = set(PARENT_MERGE_OUT.keys())
    else:
        parents_scope = {p.strip() for p in args.parents.split(",") if p.strip()}
        unknown = parents_scope - set(PARENT_MERGE_OUT.keys())
        if unknown:
            raise SystemExit(f"未知父域: {unknown}")

    sources = source_files_for_parents(root, parents_scope)
    tagged: List[Tuple[CaseBlock, str, str]] = []
    for p in sources:
        target, sub = infer_merge_target(p.name)
        if not target:
            continue
        for b in extract_blocks(p.read_text(encoding="utf-8")):
            tagged.append((b, target, sub))

    if not tagged:
        raise SystemExit("未解析到用例块")

    latest = pick_latest(tagged, add_sub_prefix=args.sub_prefix)
    trees = build_trees(latest)

    print(f"合并为 {len(trees)} 个父模块文件（共 {len(latest)} 模块键）")
    for fk in sorted(trees.keys()):
        n = sum(len(c) for c in trees[fk].values())
        print(f"  {fk}: {n} 模块, {len(trees[fk])} sheets")

    if args.dry_run:
        return

    written: Set[str] = set()
    for fk, sheets_map in trees.items():
        title = fk.replace(".md", "")
        md = csm.build_from_tree(title, sheets_map)
        if fk == "房间PK.md":
            intro = "# 房间PK\n\n> **范围**：房间 PK / 跨房 PK。\n\n---\n\n"
            if md.startswith(f"# {title}"):
                rest = md.split("\n---\n\n", 1)
                body = rest[-1] if len(rest) > 1 else md
                if body.lstrip().startswith(f"# {title}"):
                    body = body.split("\n", 1)[1]
                md = intro + body.lstrip("\n")
        (root / fk).write_text(md, encoding="utf-8")
        written.add(fk)

  # 仅删除本次合并消耗的子模块文件
    consumed = {p.name for p in sources}
    for name in sorted(consumed):
        if name not in written and name not in PRESERVE_ALWAYS:
            p = root / name
            if p.exists():
                p.unlink()
                print(f"  删除子模块: {name}")

    subprocess.run(
        [sys.executable, str(SCRIPTS / "kb_clean_toc_titles.py"), "--root", str(root)],
        check=False,
    )

    opt = SCRIPTS / "optimize_kb_docs.py"
    if opt.exists():
        subprocess.run(
            [sys.executable, str(opt), "--root", str(root)],
            check=False,
        )

    print(f"merge-parents done -> {root}")


if __name__ == "__main__":
    main()
