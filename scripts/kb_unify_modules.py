#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知识库文件名唯一化 + 应合并子域合并。

- 消除重复命名（如 币商-币商、家族-家族房间）
- 将「优化杂项」「通用」及过小碎片并入「综合」
- 语义相近子域合并（如 红包+宝箱）
- 输出唯一文件名
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent / "documents" / "documents"
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

# (parent, 原子域) -> 唯一文件名（不含 .md、不含连字符 -）
CANONICAL_FILE: Dict[Tuple[str, str], str] = {}


def _reg(parent: str, subs: List[str], filename: str) -> None:
    for s in subs:
        CANONICAL_FILE[(parent, s)] = filename


def _join(parent_label: str, sub_label: str) -> str:
    """父模块名 + 子域名，中间不加 -。"""
    return f"{parent_label}{sub_label}"


# ---------- 房间 ----------
_reg("room", ["麦位"], _join("房间", "麦位"))
_reg("room", ["进房"], _join("房间", "进房"))
_reg("room", ["红包", "宝箱"], _join("房间", "红包与宝箱"))
_reg("room", ["成员管理", "等级特权"], _join("房间", "成员与等级"))
_reg("room", ["界面运营"], _join("房间", "界面与运营"))
_reg("room", ["房内礼物"], _join("房间", "房内礼物"))
_reg("room", ["家族房间"], _join("房间", "家族房"))
_reg("room", ["优化杂项", "通用"], _join("房间", "综合"))

# ---------- 礼物 ----------
_reg("gift", ["面板送礼"], _join("礼物", "面板与送礼"))
_reg("gift", ["神秘人"], _join("礼物", "神秘人"))
_reg("gift", ["勋章展馆"], _join("礼物", "勋章与展馆"))
_reg("gift", ["贵族VIP"], _join("礼物", "贵族与VIP"))
_reg("gift", ["背包"], _join("礼物", "背包"))
_reg(
    "gift",
    ["优化杂项", "通用", "互动礼物", "幸运礼物", "定制礼物", "服务迁移"],
    _join("礼物", "综合"),
)

# ---------- 消息 ----------
_reg("message", ["私聊群聊"], _join("消息", "私聊与群聊"))
_reg("message", ["IM功能"], _join("消息", "IM"))
_reg("message", ["关系"], _join("消息", "关系链"))
_reg("message", ["礼物消息"], _join("消息", "礼物与打赏"))
_reg(
    "message",
    ["优化杂项", "通用", "客户端", "通知红点"],
    _join("消息", "综合"),
)

# ---------- 币商 ----------
_reg("coin", ["充值"], _join("币商", "充值"))
_reg("coin", ["提现转账"], _join("币商", "提现与转账"))
_reg("coin", ["币商"], _join("币商", "商户业务"))
_reg("coin", ["优化杂项", "通用", "钻石明细"], _join("币商", "综合"))

# ---------- 家族 ----------
_reg("family", ["创建加入"], _join("家族", "创建与加入"))
_reg("family", ["成员管理"], _join("家族", "成员管理"))
_reg("family", ["任务等级"], _join("家族", "任务与等级"))
_reg("family", ["家族房间", "通用"], _join("家族", "综合"))

# ---------- 主题房 / 动态 / 其他 / 客服 ----------
_reg("theme_room", ["主题活动"], _join("主题房", "活动"))
_reg("theme_room", ["优化杂项"], _join("主题房", "综合"))
_reg("moments", ["发布浏览"], _join("动态", "发布与浏览"))
_reg("moments", ["审核", "优化杂项", "通用"], _join("动态", "综合"))
_reg("other", ["账号注册"], _join("其他", "账号与注册"))
_reg("other", ["分区策略"], _join("其他", "分区策略"))
_reg("other", ["活动运营"], _join("其他", "活动运营"))
_reg("other", ["优化杂项", "通用"], _join("其他", "综合"))
_reg("customer_service", ["客服"], _join("客服", "客服"))
_reg("customer_service", ["优化杂项", "通用"], _join("客服", "综合"))
_reg("super_admin", ["超管审核"], _join("超管", "审核"))
_reg("super_admin", ["优化杂项", "通用"], _join("超管", "综合"))

# 单文件父域
SINGLE_CANONICAL: Dict[str, str] = {
    "room_pk": "房间PK",
    "game": "游戏",
    "agency": "公会",
    "rank_activity": "榜单与活动",
    "face_auth": "人脸认证",
}

PARENT_CN_FALLBACK: Dict[str, str] = {
    "room": "房间",
    "gift": "礼物",
    "message": "消息",
    "coin": "币商",
    "family": "家族",
    "theme_room": "主题房",
    "moments": "动态",
    "other": "其他",
    "customer_service": "客服",
    "super_admin": "超管",
    **SINGLE_CANONICAL,
}


def canonical_filename(parent: str, sub: str) -> str:
    if parent in SINGLE_CANONICAL and not sub:
        return f"{SINGLE_CANONICAL[parent]}.md"
    key = (parent, sub)
    if key in CANONICAL_FILE:
        return f"{CANONICAL_FILE[key]}.md"
    label = PARENT_CN_FALLBACK.get(parent, parent)
    return f"{label}{sub}.md" if sub else f"{label}.md"


def resolve_canonical(parent: str, sub: str) -> str:
    """返回唯一目标文件名。"""
    key = (parent, sub)
    if key in CANONICAL_FILE:
        return f"{CANONICAL_FILE[key]}.md"
    if parent in SINGLE_CANONICAL:
        return f"{SINGLE_CANONICAL[parent]}.md"
    label = PARENT_CN_FALLBACK.get(parent, parent)
    safe_sub = sub or "综合"
    return f"{label}{safe_sub}.md"


def pick_latest(blocks: List[CaseBlock]) -> Dict[Tuple[str, str, str], CaseBlock]:
    best: Dict[Tuple[str, str, str], CaseBlock] = {}
    for b in blocks:
        parent = csm.classify_target(b)
        sub = kb_split.classify_sub(parent, b.sheet or "", b.module or "", b.body)
        fname = resolve_canonical(parent, sub)
        key = (fname, b.sheet or "未归类需求", kb_split.norm_module_key(b.module))
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
    ap = argparse.ArgumentParser(description="知识库文件名唯一化与合并")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root: Path = args.root

    blocks = kb_split.load_blocks(root)
    latest = pick_latest(blocks)
    trees = build_trees(latest)

    # 校验文件名唯一
    assert len(trees) == len(set(trees.keys()))

    print(f"唯一化后 {len(trees)} 个文件（原 {len(list(root.glob('*.md')))} 个 md）")
    for fk in sorted(trees.keys(), key=lambda x: -sum(len(c) for c in trees[x].values())):
        n = sum(len(c) for c in trees[fk].values())
        print(f"  {fk}: {n} 模块")

    if args.dry_run:
        return

    written: Set[str] = set()
    for fk, sheets_map in trees.items():
        title = fk.replace(".md", "")
        md = csm.build_from_tree(title, sheets_map)
        if fk == "房间PK.md":
            intro = "# 房间PK\n\n> **范围**：房间 PK / 跨房 PK 全流程。\n\n---\n\n"
            if md.startswith(f"# {title}"):
                rest = md.split("\n---\n\n", 1)
                body = rest[-1] if len(rest) > 1 else md
                if body.lstrip().startswith(f"# {title}"):
                    body = body.split("\n", 1)[1]
                md = intro + body.lstrip("\n")
        (root / fk).write_text(md, encoding="utf-8")
        written.add(fk)

    keep = written | {"README.md"}
    for p in root.glob("*.md"):
        if p.name not in keep and not p.name.startswith("_"):
            p.unlink()
            print(f"  删除旧文件: {p.name}")

    opt = SCRIPTS / "optimize_kb_docs.py"
    if opt.exists():
        subprocess.run(
            [sys.executable, str(opt), "--root", str(root)],
            check=False,
        )

    print(f"unify done -> {root}")


if __name__ == "__main__":
    main()
