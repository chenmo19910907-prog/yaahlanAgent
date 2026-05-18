#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按修正后的 classify_target 规则重新划分知识库并写回。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent / "documents" / "documents"


def _load_module(name: str, path: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


content_opt = _load_module("content_opt", SCRIPTS / "content_optimize_kb_docs.py")
csm = _load_module("content_split", SCRIPTS / "content_split_merge_kb.py")
kb_feat = _load_module("kb_feat", SCRIPTS / "kb_extract_features.py")

classify_target = csm.classify_target
build_trees = kb_feat.build_trees
classify_feature = kb_feat.classify_feature
normalize_feature_sheet = kb_feat.normalize_feature_sheet
pick_latest = kb_feat.pick_latest
extract_blocks = content_opt.extract_blocks
CaseBlock = content_opt.CaseBlock


def load_all(root: Path):
    out = []
    for p in sorted(root.glob("*.md")):
        if p.name.startswith("_") or p.name.lower() == "readme.md":
            continue
        for b in extract_blocks(p.read_text(encoding="utf-8")):
            out.append((b, p.name))
    return out

PARENT_MAP = {
    "room": "房间.md",
    "room_pk": "房间PK.md",
    "gift": "礼物.md",
    "message": "消息.md",
    "coin": "币商.md",
    "family": "家族.md",
    "theme_room": "主题房.md",
    "moments": "动态.md",
    "other": "其他模块.md",
    "customer_service": "客服.md",
    "super_admin": "超管.md",
    "game": "游戏.md",
    "agency": "公会.md",
    "rank_activity": "榜单与活动.md",
    "face_auth": "人脸认证.md",
    "auth_login": "注册登录.md",
}

PARENT_LABELS = (
    "房间",
    "房间PK",
    "礼物",
    "消息",
    "币商",
    "家族",
    "主题房",
    "动态",
    "其他模块",
    "客服",
    "超管",
    "客服与超管",
    "游戏",
    "公会",
    "公会与AM",
    "榜单与活动",
    "账号与安全",
    "注册登录",
    "人脸认证",
    "充值提现转账",
    "神秘人",
    "VIP",
    "特权VIP",
    "贵族",
    "财富等级",
    "收藏展馆",
    "房间红包",
    "房间成员",
)


def _strip_cross_prefixes(sheet: str, target_file: str) -> str:
    sn = (sheet or "未归类需求").strip()
    target_label = target_file.replace(".md", "")
    changed = True
    while changed:
        changed = False
        for label in PARENT_LABELS:
            if label == target_label:
                continue
            pref = f"{label}·"
            if sn.startswith(pref):
                sn = sn[len(pref) :]
                changed = True
    return sn or "未归类需求"


INTROS = {
    "客服.md": "> **范围**：客服系统、券包下发、快捷回复、客服评价、帮助中心等。\n",
    "超管.md": "> **范围**：超管后台、审核、设备拉黑、工单、权限与运营审核等。\n",
    "神秘人.md": "> **范围**：神秘人身份、特权页、资料卡、语音变声等强相关能力。\n",
    kb_feat.VIP_MD: "> **范围**：特权 VIP 等级、成长值、专属特权、定制头像框、自定义座驾、VIP 客服等。\n",
    "贵族.md": "> **范围**：贵族等级、特权、贵族礼物与展示等强相关能力。\n",
    "财富等级.md": "> **范围**：财富/魅力等级、等级改版与进度等强相关能力。\n",
    "收藏展馆.md": "> **范围**：收藏展馆、礼物展馆、道具展馆、成就收藏、礼物收集挑战等强相关能力（弱相关仍留各父模块）。\n",
    "注册登录.md": "> **范围**：注册、登录、注销、账号绑定、密码与白名单等强相关能力。\n",
    kb_feat.CP_RELATIONSHIP_MD: (
        "> **范围**：CP/好友关系、亲密度、关系空间、关系特权、关系外显、"
        "组建/解除关系等强相关能力（弱相关仍留各父模块）。\n"
    ),
    kb_feat.PROFILE_HOME_MD: (
        "> **范围**：个人主页（profile）、资料页、资料编辑/修改、靓号、"
        "资料页背景、谁看过我等强相关能力。\n"
    ),
    kb_feat.OUTFIT_MD: (
        "> **范围**：装扮商城、我的装扮、装扮购买与佩戴/使用、"
        "头像框/座驾/入场条/聊天气泡等装扮道具。\n"
    ),
    "币商.md": (
        "> **范围**：币商身份、押金缴纳/退回、商户榜单、币商运营位、"
        "币商充值真人认证、币商 icon 等强相关能力。"
        "充值/提现/转账见 [`充值提现转账.md`](充值提现转账.md)。\n"
    ),
    "充值提现转账.md": (
        "> **范围**：用户/币商充值、提现、转账、钻石明细、钱包转账 UI、"
        "稳定币充值等（不含币商身份与押金本体，见 [`币商.md`](币商.md)）。\n"
    ),
}

# 不参与全量重写的独立/切片文件（房间红包成员在重分类后由 extract 脚本再生）
PRESERVE_ALWAYS = frozenset(
    {
        "README.md",
    }
)

STANDALONE_OUTPUT = frozenset(
    {
        "房间PK.md",
        "游戏.md",
        "公会.md",
        "客服.md",
        "超管.md",
        "榜单与活动.md",
        "注册登录.md",
        "人脸认证.md",
    }
)

COIN_SPLIT_FILES = frozenset({"币商.md", "充值提现转账.md"})

ROOM_SLICE_FILES = frozenset({"房间红包.md", "房间成员.md"})


def main() -> None:
    ap = argparse.ArgumentParser(description="重新划分知识库业务域")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root: Path = args.root

    raw = load_all(root)  # type: ignore[assignment]
    tagged = []
    moved: dict[str, int] = defaultdict(int)

    for b, origin in raw:
        sheet = (b.sheet or "").strip()
        if csm.is_default_sheet_name(sheet):
            continue
        mod_clean = content_opt.SAME_AS_SUFFIX_RE.sub("", b.module or "").strip()
        if sheet in ("未归类需求", "") and not mod_clean and not (b.body or "").strip():
            continue
        parent = classify_target(b)
        feat = classify_feature(b)
        if feat:
            target = feat
            sheet = normalize_feature_sheet(
                PARENT_MAP.get(parent, origin), b, feat
            )
            moved[f"->{feat}"] += 1
        else:
            target = PARENT_MAP.get(parent, "其他模块.md")
            sheet = _strip_cross_prefixes(b.sheet or "未归类需求", target)
            moved[target] += 1
        tagged.append((b, target, sheet))

    latest = pick_latest(tagged)
    trees = build_trees(latest)

    print(f"重分类后 {len(trees)} 个文件, {len(latest)} 模块键")
    for fk in sorted(trees.keys(), key=lambda x: -sum(len(c) for c in trees[x].values())):
        print(f"  {fk}: {sum(len(c) for c in trees[fk].values())} 模块")

    if args.dry_run:
        return

    written: set[str] = set()
    for fk, sheets_map in trees.items():
        title = "特权VIP" if fk == kb_feat.VIP_MD else fk.replace(".md", "")
        md = csm.build_from_tree(title, sheets_map)
        if fk in INTROS and md.startswith(f"# "):
            rest = md.split("\n---\n\n", 1)
            body = rest[-1] if len(rest) > 1 else md
            if body.lstrip().startswith(f"# {title}"):
                body = body.split("\n", 1)[1]
            md = f"# {title}\n\n{INTROS[fk]}\n---\n\n" + body.lstrip("\n")
        if fk == "房间PK.md" and md.startswith("# 房间PK"):
            rest = md.split("\n---\n\n", 1)
            body = rest[-1] if len(rest) > 1 else md
            if body.lstrip().startswith("# 房间PK"):
                body = body.split("\n", 1)[1]
            md = "# 房间PK\n\n> **范围**：房间 PK / 跨房 PK。\n\n---\n\n" + body.lstrip(
                "\n"
            )
        (root / fk).write_text(md, encoding="utf-8")
        written.add(fk)

    # 房间红包/成员：从 房间.md 拆出强相关切片
    extract_room = SCRIPTS / "kb_extract_room_modules.py"
    if extract_room.exists():
        subprocess.run(
            [sys.executable, str(extract_room), "--root", str(root)],
            check=False,
        )
        written.update(ROOM_SLICE_FILES)

    extract_feat = SCRIPTS / "kb_extract_features.py"
    if extract_feat.exists():
        subprocess.run(
            [sys.executable, str(extract_feat), "--root", str(root)],
            check=False,
        )
        written.update(kb_feat.FEATURE_FILES)

    split_coin = SCRIPTS / "kb_split_submodules.py"
    if split_coin.exists():
        subprocess.run(
            [
                sys.executable,
                str(split_coin),
                "--root",
                str(root),
                "--parents",
                "coin",
            ],
            check=False,
        )
        written.update(COIN_SPLIT_FILES)

    for p in root.glob("*.md"):
        if (
            p.name not in written
            and p.name not in PRESERVE_ALWAYS
            and p.name not in STANDALONE_OUTPUT
            and p.name not in ROOM_SLICE_FILES
            and p.name not in COIN_SPLIT_FILES
            and not p.name.startswith("_")
        ):
            p.unlink()
            print(f"  删除: {p.name}")

    opt = SCRIPTS / "optimize_kb_docs.py"
    if opt.exists():
        subprocess.run(
            [sys.executable, str(opt), "--root", str(root)],
            check=False,
        )

    subprocess.run(
        [sys.executable, str(SCRIPTS / "kb_clean_toc_titles.py"), "--root", str(root)],
        check=False,
    )

    print(f"reclassify done -> {root}")


if __name__ == "__main__":
    main()
