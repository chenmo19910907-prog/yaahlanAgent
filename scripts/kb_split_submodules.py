#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将体量过大的知识库 md 按子业务域拆分为多个文件。

命名：房间域为 房间红包.md、房间成员.md；其它父域为 {父模块}-{子域}.md
体量较小或未列入拆分列表的域保持单文件（游戏.md、房间PK.md 等）。

房间/礼物请保持 房间.md、礼物.md 单文件；独立功能见 kb_extract_features（神秘人/VIP/贵族/财富等级）与 房间PK.md。
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from project_paths import testcase_kb_root  # noqa: E402

ROOT = testcase_kb_root()
from typing import Dict, List, Tuple


SCRIPTS = Path(__file__).resolve().parent

_SPEC_OPT = importlib.util.spec_from_file_location(
    "content_opt",
    SCRIPTS / "content_optimize_kb_docs.py",
)
content_opt = importlib.util.module_from_spec(_SPEC_OPT)
sys.modules["content_opt"] = content_opt
assert _SPEC_OPT.loader is not None
_SPEC_OPT.loader.exec_module(content_opt)

_SPEC_SPLIT = importlib.util.spec_from_file_location(
    "content_split",
    SCRIPTS / "content_split_merge_kb.py",
)
csm = importlib.util.module_from_spec(_SPEC_SPLIT)
sys.modules["content_split"] = csm
assert _SPEC_SPLIT.loader is not None
_SPEC_SPLIT.loader.exec_module(csm)

CaseBlock = content_opt.CaseBlock
extract_blocks = content_opt.extract_blocks
SAME_AS_SUFFIX_RE = content_opt.SAME_AS_SUFFIX_RE

# 需要拆子文件的父域（房间/礼物仅保留父模块单文件 + 独立功能库，勿拆细）
SPLIT_PARENTS = frozenset(
    {
        "message",
        "coin",
        "other",
        "customer_service",
        "super_admin",
        "family",
        "theme_room",
        "moments",
    }
)

PARENT_CN: Dict[str, str] = {
    "room_pk": "房间PK",
    "room": "房间",
    "gift": "礼物",
    "family": "家族",
    "theme_room": "主题房",
    "moments": "动态",
    "message": "消息",
    "face_auth": "人脸认证",
    "customer_service": "客服",
    "super_admin": "超管",
    "agency": "公会",
    "coin": "币商",
    "game": "游戏",
    "rank": "榜单",
    "activity": "活动",
    "other": "其他",
}

# 独立功能库，任何拆分模式下均不删除
PRESERVE_FILES = frozenset(
    {
        "神秘人.md",
        "特权VIP.md",
        "贵族.md",
        "财富等级.md",
        "收藏展馆.md",
        "房间PK.md",
        "房间红包.md",
        "房间成员.md",
        "房间麦位.md",
        "房间进房.md",
        "房间红包.md",
        "房间成员.md",
        "房间界面.md",
        "房间优化.md",
        "房间家族房.md",
        "房间其他.md",
        "房间等级.md",
        "房间房内礼物.md",
        "房间红包.md",
        "房间成员.md",
        "游戏.md",
        "公会.md",
        "榜单.md",
        "活动.md",
        "注册登录.md",
        "人脸认证.md",
        "客服.md",
        "超管.md",
        "充值提现转账.md",
        "README.md",
    }
)

# 房间子域 -> 输出文件名（无连字符，与 房间PK.md 一致）
ROOM_SUB_FILENAME: Dict[str, str] = {
    "麦位": "房间麦位.md",
    "进房": "房间进房.md",
    "红包": "房间红包.md",
    "宝箱": "房间宝箱.md",
    "成员管理": "房间成员.md",
    "等级特权": "房间等级.md",
    "界面运营": "房间界面.md",
    "家族房间": "房间家族房.md",
    "房内礼物": "房间房内礼物.md",
    "优化杂项": "房间优化.md",
    "通用": "房间其他.md",
}

# 币商域子域 -> 输出文件名（充值/提现/转账合并；币商.md 仅强相关）
COIN_SUB_FILENAME: Dict[str, str] = {
    "币商": "币商.md",
    "充值": "充值提现转账.md",
    "提现": "充值提现转账.md",
    "转账": "充值提现转账.md",
    "钻石明细": "充值提现转账.md",
    "稳定币": "充值提现转账.md",
    "通用": "币商.md",
    "优化杂项": "币商.md",
}

# 币商域拆分后的旧文件名（合并时需删除）
COIN_LEGACY_SPLIT_FILES = frozenset({"充值.md", "提现.md", "转账.md"})

# 礼物子域 -> 输出文件名
GIFT_SUB_FILENAME: Dict[str, str] = {
    "勋章展馆": "礼物勋章展馆.md",
    "面板送礼": "礼物面板送礼.md",
    "背包": "礼物背包.md",
    "幸运礼物": "礼物幸运礼物.md",
    "互动礼物": "礼物互动.md",
    "房内礼物": "礼物房内.md",
    "收集挑战": "礼物收集挑战.md",
    "定制礼物": "礼物定制.md",
    "服务迁移": "礼物服务迁移.md",
    "关系": "礼物关系.md",
    "优化杂项": "礼物优化.md",
    "通用": "礼物其他.md",
}

# 拆分后不再保留的整文件
LEGACY_MONOLITH: Dict[str, str] = {
    "room": "房间.md",
    "gift": "礼物.md",
    "message": "消息.md",
    "coin": "币商.md",
    "customer_service": "客服.md",
    "super_admin": "超管.md",
    "family": "家族.md",
    "theme_room": "主题房.md",
    "moments": "动态.md",
}

# 保持单文件的父域 -> 文件名
SINGLE_FILE: Dict[str, str] = {
    "room_pk": "房间PK.md",
    "game": "游戏.md",
    "agency": "公会.md",
    "rank": "榜单.md",
    "activity": "活动.md",
    "face_auth": "人脸认证.md",
    "auth_login": "注册登录.md",
}

# (parent) -> [(pattern, sub_key)] 先匹配先生效
SUB_RULES: Dict[str, List[Tuple[re.Pattern[str], str]]] = {
    "room": [
        (re.compile(r"麦位|20麦|上麦|下麦|环绕|语音房麦位|体验卡|自定义表情|付费表情"), "麦位"),
        (re.compile(r"进房|服务端进房|deeplink|分享|收听|欢迎消息|入场条|冷起首帧"), "进房"),
        (re.compile(r"红包与宝箱|红包"), "红包"),
        (re.compile(r"宝箱"), "宝箱"),
        (re.compile(r"成员与等级|成员|管理员|移除|门槛|房间搜索|封禁列表|操作记录"), "成员管理"),
        (re.compile(r"等级|热度|小时榜|装扮|装饰|个人主页装饰"), "等级特权"),
        (re.compile(r"背景|边框|UI改版|资料卡|帧|tab|首页|弹窗|列表边框"), "界面运营"),
        (re.compile(r"家族房间"), "家族房间"),
        (re.compile(r"房内|房间内.*送礼|礼物展馆|心愿礼物"), "房内礼物"),
        (re.compile(r"优化|技术优化|Android|域名"), "优化杂项"),
    ],
    "gift": [
        (re.compile(r"勋章与展馆|国家勋章|成就收藏|定制头像框|平台标签调整"), "勋章展馆"),
        (re.compile(r"互动礼物"), "互动礼物"),
        (re.compile(r"礼物收集挑战|收集挑战"), "收集挑战"),
        (re.compile(r"房内礼物"), "房内礼物"),
        (re.compile(r"背包"), "背包"),
        (re.compile(r"幸运|返钻|祈愿"), "幸运礼物"),
        (re.compile(r"定制礼物|定制头像|违规提示"), "定制礼物"),
        (re.compile(r"礼物服务迁移|Redis迁移|礼物事件"), "服务迁移"),
        (re.compile(r"关系改版|亲密度|组成关系"), "关系"),
        (re.compile(r"礼物面板|面板与送礼|送礼|选中礼物|面板排序|非房间内礼物"), "面板送礼"),
        (re.compile(r"优化|Android|域名|不跟版"), "优化杂项"),
    ],
    "message": [
        (re.compile(r"^IM|IM\s|IM新增|IM UI|回复.+消息|转发消息|换行|置顶"), "IM功能"),
        (re.compile(r"私聊|群聊|会话|聊天列表|陌生人|1V1|1v1"), "私聊群聊"),
        (re.compile(r"关系改版|组成关系|建联|关系空间|亲密度"), "关系"),
        (re.compile(r"礼物消息|送礼|钻石到账|礼物面板"), "礼物消息"),
        (re.compile(r"红点|push|通知|提醒"), "通知红点"),
        (re.compile(r"iOS|ios|Android|安卓|客户端"), "客户端"),
        (re.compile(r"优化|分区策略|设备拉黑"), "优化杂项"),
    ],
    "coin": [
        (re.compile(r"钱包转账|充值·钱包转账"), "转账"),
        (
            re.compile(
                r"币商·充值·币商押金|币商押金退回|商户业务|币商功能|币商icon|"
                r"币商列表|币商客户|币商充值增加|币商功能升级|不同模式运营位"
            ),
            "币商",
        ),
        (re.compile(r"币商·充值|充值·"), "充值"),
        (re.compile(r"币商·提现与转账·.*转账|转账|钱包转账"), "转账"),
        (re.compile(r"币商·提现与转账|币商·提现|提现|预提|自提|yaahlan|薪资"), "提现"),
        (
            re.compile(
                r"^币商·|币商大额|币商退回|币商白名单|"
                r"币商押金|币商视角",
            ),
            "币商",
        ),
        (re.compile(r"充值|限额|避审|支付|WEB充值|防控|首充|印度不下发"), "充值"),
        (re.compile(r"提现|预提|自提|yaahlan|薪资"), "提现"),
        (re.compile(r"转账|钱包转账"), "转账"),
        (re.compile(r"钻石明细|钻石到账|钻石补偿"), "钻石明细"),
        (re.compile(r"稳定币"), "稳定币"),
        (re.compile(r"优化|域名|懒加载|广播分流"), "优化杂项"),
    ],
    "customer_service": [
        (re.compile(r"客服|快捷回复|券包"), "客服"),
        (re.compile(r"优化"), "优化杂项"),
    ],
    "super_admin": [
        (re.compile(r"超管|审核|拉黑|工单|后台|设备"), "超管审核"),
        (re.compile(r"优化"), "优化杂项"),
    ],
    "family": [
        (re.compile(r"创建|加入|广场|招募"), "创建加入"),
        (re.compile(r"成员|管理|族长|踢出"), "成员管理"),
        (re.compile(r"任务|基金|等级|榜单"), "任务等级"),
        (re.compile(r"群聊|家族房间|主页"), "家族房间"),
        (re.compile(r"优化|改版"), "优化杂项"),
    ],
    "theme_room": [
        (re.compile(r"主题|活动房|创建"), "主题活动"),
        (re.compile(r"优化"), "优化杂项"),
    ],
    "moments": [
        (re.compile(r"发布|帖子|视频|动态|moment"), "发布浏览"),
        (re.compile(r"审核|违规|举报"), "审核"),
        (re.compile(r"优化|标签|热榜"), "优化杂项"),
    ],
    "other": [
        (re.compile(r"注册|登录|账号|昵称"), "账号注册"),
        (re.compile(r"分区|数据隔离|大区|跨区"), "分区策略"),
        (re.compile(r"活动|盛典|banner"), "活动运营"),
        (re.compile(r"优化|Android|Redis|Sheet"), "优化杂项"),
    ],
}


def norm_module_key(module: str) -> str:
    s = SAME_AS_SUFFIX_RE.sub("", module or "").strip()
    s = re.sub(r"^\d+[、.．\s]*", "", s)
    return re.sub(r"\s+", "", s).lower()


def classify_sub(parent: str, sheet: str, module: str, body: str) -> str:
    rules = SUB_RULES.get(parent)
    if not rules:
        return ""
    blob = f"{sheet} {module} {body}"
    for pat, sub in rules:
        if pat.search(blob):
            return sub
    return "通用"


def output_filename(parent: str, sub: str) -> str:
    if parent == "room" and sub:
        return ROOM_SUB_FILENAME.get(sub, f"房间{sub}.md")
    if parent == "gift" and sub:
        return GIFT_SUB_FILENAME.get(sub, f"礼物{sub}.md")
    if parent == "coin" and sub:
        return COIN_SUB_FILENAME.get(sub, f"币商{sub}.md")
    label = PARENT_CN.get(parent, parent)
    if parent in SPLIT_PARENTS and sub:
        return f"{label}-{sub}.md"
    return SINGLE_FILE.get(parent, f"{label}.md")


def load_blocks(root: Path, source_names: frozenset[str] | None = None) -> List[CaseBlock]:
    blocks: List[CaseBlock] = []
    for p in sorted(root.glob("*.md")):
        if p.name.startswith("_") or p.name.lower() in ("readme.md",):
            continue
        if source_names is not None and p.name not in source_names:
            continue
        blocks.extend(extract_blocks(p.read_text(encoding="utf-8")))
    return blocks


def pick_latest(
    blocks: List[CaseBlock],
    parents_scope: frozenset[str],
) -> Dict[Tuple[str, str, str, str], CaseBlock]:
    best: Dict[Tuple[str, str, str, str], CaseBlock] = {}
    for b in blocks:
        parent = csm.classify_target(b)
        if parent not in parents_scope:
            continue
        sheet = b.sheet or "未归类需求"
        if csm.is_default_sheet_name(sheet):
            continue
        sub = classify_sub(parent, sheet, b.module or "", b.body)
        key = (
            parent,
            sub,
            b.sheet or "未归类需求",
            norm_module_key(b.module),
        )
        if key not in best or b.version_tuple > best[key].version_tuple:
            best[key] = b
    return best


def build_trees(
    latest: Dict[Tuple[str, str, str, str], CaseBlock],
) -> Dict[str, Dict[str, Dict[str, Dict[str, List[CaseBlock]]]]]:
    """file_key -> sheet -> cluster -> blocks"""
    trees: Dict[str, Dict[str, Dict[str, List[CaseBlock]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for (parent, sub, sheet, _mod_key), b in latest.items():
        fk = output_filename(parent, sub)
        cluster = csm.merge_cluster_key(sheet, b.module)
        bucket = trees[fk][sheet][cluster]
        if not any(x.module == b.module for x in bucket):
            bucket.append(b)
    return trees


def main() -> None:
    ap = argparse.ArgumentParser(description="知识库拆分为更多子模块文件")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument(
        "--parents",
        type=str,
        default="all",
        help="要拆分的父域，逗号分隔：room,gift,... 或 all",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root: Path = args.root

    if args.parents.strip().lower() == "all":
        parents_scope = SPLIT_PARENTS
        source_names = None
    else:
        parents_scope = frozenset(p.strip() for p in args.parents.split(",") if p.strip())
        unknown = parents_scope - SPLIT_PARENTS
        if unknown:
            raise SystemExit(f"未知父域: {unknown}，可选: {sorted(SPLIT_PARENTS)}")
        if "coin" in parents_scope:
            source_names = frozenset(
                {"币商.md", "充值提现转账.md", "充值.md", "提现.md", "转账.md"}
            )
        else:
            source_names = frozenset(
                LEGACY_MONOLITH[p] for p in parents_scope if p in LEGACY_MONOLITH
            )

    blocks = load_blocks(root, source_names)
    if not blocks:
        raise SystemExit("未解析到用例块")

    latest = pick_latest(blocks, parents_scope)
    trees = build_trees(latest)

    print(f"将写入 {len(trees)} 个子模块文件（来源 {len(blocks)} 块 -> {len(latest)} 键）")
    for fk in sorted(trees.keys(), key=lambda x: -sum(len(c) for c in trees[x].values())):
        n = sum(len(c) for c in trees[fk].values())
        print(f"  {fk}: {n} 模块")

    if args.dry_run:
        return

    written: List[Path] = []
    for fk, sheets_map in trees.items():
        title = fk.replace(".md", "")
        md = csm.build_from_tree(title, sheets_map)
        if fk == "房间PK.md":
            pk_map = (
                "## 知识地图（阶段）\n\n"
                "| 阶段 | 常见 Sheet |\n"
                "|------|------------|\n"
                "| 邀请与撮合 | PK邀请和匹配 |\n"
                "| 开局前 | PK准备 |\n"
                "| 进行中 | PK流程、乱斗PK、团战PK |\n"
                "| 结束 | PK关闭 |\n"
                "| 双房操作 | PK房间操作 |\n"
                "| 跨房/运营 | 跨房PK优化、跨房PK分区策略优化、PK提款机 |\n\n"
                "---\n\n"
            )
            intro = (
                "# 房间PK\n\n"
                "> **范围**：房间内 PK、跨房 PK、乱斗/团战/团队 PK。\n\n"
                "---\n\n"
                f"{pk_map}"
            )
            if md.startswith(f"# {title}"):
                rest = md.split("\n---\n\n", 1)
                body = rest[-1] if len(rest) > 1 else md
                if body.lstrip().startswith(f"# {title}"):
                    body = body.split("\n", 1)[1]
                md = intro + body.lstrip("\n")
        path = root / fk
        path.write_text(md, encoding="utf-8")
        written.append(path)

    # 删除本次拆分范围内的旧大文件（若子域已复用同名文件则保留）
    for parent in parents_scope:
        legacy = LEGACY_MONOLITH.get(parent)
        if not legacy or legacy in trees:
            continue
        p = root / legacy
        if p.exists():
            p.unlink()
            print(f"  删除旧文件: {legacy}")

    if "coin" in parents_scope:
        for name in COIN_LEGACY_SPLIT_FILES:
            p = root / name
            if p.exists() and name not in {x.name for x in written}:
                p.unlink()
                print(f"  删除旧文件: {name}")

    # 全量拆分时：删除其它未写入的残留子文件；仅拆 room 时不删其它 md
    if args.parents.strip().lower() == "all":
        keep_names = {p.name for p in written} | PRESERVE_FILES
        for p in root.glob("*.md"):
            if p.name not in keep_names and not p.name.startswith("_"):
                p.unlink()
                print(f"  删除残留: {p.name}")

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

    print(f"split-submodules done -> {root} ({len(written)} files)")


if __name__ == "__main__":
    main()
