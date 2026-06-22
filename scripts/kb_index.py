"""知识库模块名与路径索引（供 suggest_kb、coverage 等脚本复用）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class KbHit:
    kind: str
    path: Path
    note: str = ""


# 关键词（小写）→ 模块键；匹配任一关键词即命中
MODULE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "gift": ("礼物", "送礼", "背包", "gift", "勋章", "定制礼物"),
    "room": ("房间", "麦位", "进房", "语音房", "room"),
    "room_pk": ("pk", "跨房", "房间pk"),
    "rank": ("榜单", "排行", "打榜", "荣誉墙", "全服榜", "room页榜单"),
    "activity": ("活动", "活动条", "抽奖", "兑换", "年末盛典", "摩天轮", "周年庆"),
    "family": ("家族", "声望", "基金"),
    "theme_room": ("主题房",),
    "moments": ("动态", "moment", "moments", "发布动态"),
    "message": ("消息", "im", "私聊", "群聊"),
    "vip": ("vip", "特权vip", "成长值"),
    "noble": ("贵族",),
    "wealth": ("财富", "魅力等级", "财富等级"),
    "auth_login": ("登录", "注册", "注销", "账号"),
    "face_auth": ("真人认证", "人脸", "实名"),
    "coin": ("充值", "提现", "转账", "钻石", "币商", "钱包"),
    "agency": ("公会", "公会长", "agency"),
    "customer_service": ("客服", "建联"),
    "super_admin": ("超管", "审核", "工单"),
    "game": ("游戏", "捕鱼"),
    "profile": ("个人主页", "资料页", "profile"),
    "cp": ("cp", "好友关系", "亲密度"),
    "dress": ("装扮",),
    "mystery": ("神秘人",),
    "collector": ("收藏展馆",),
}

MODULE_FILES = {
    "gift": {
        "documents": ("gift.md",),
        "testcase_kb": ("礼物.md",),
        "bug_kb": ("礼物.md",),
        "templates": ("抽奖.md", "yaahlan榜单.md"),
    },
    "room": {
        "documents": ("room/",),
        "testcase_kb": ("房间.md",),
        "bug_kb": ("房间.md",),
        "templates": ("房间大入口.md",),
    },
    "room_pk": {
        "documents": ("room/",),
        "testcase_kb": ("房间PK.md",),
        "bug_kb": ("房间PK.md",),
    },
    "rank": {
        "testcase_kb": ("榜单.md",),
        "bug_kb": ("榜单.md",),
        "templates": ("yaahlan榜单.md",),
    },
    "activity": {
        "testcase_kb": ("活动.md",),
        "bug_kb": ("活动.md",),
        "templates": ("**/",),
    },
    "family": {
        "documents": ("家族改版.md",),
        "testcase_kb": ("家族.md",),
        "bug_kb": ("家族.md",),
    },
    "theme_room": {
        "documents": ("room/活动主题房.md", "主题房.md"),
        "testcase_kb": ("主题房.md",),
        "bug_kb": ("主题房.md",),
    },
    "moments": {
        "documents": ("moments/basic module.md", "moments/video.md", "moments/hot.md", "moments/label.md"),
        "testcase_kb": ("动态.md",),
        "bug_kb": ("动态.md",),
    },
    "message": {
        "documents": ("消息.md",),
        "testcase_kb": ("消息.md",),
        "bug_kb": ("消息.md",),
    },
    "vip": {
        "documents": ("vip等级.md",),
        "testcase_kb": ("特权VIP.md",),
        "bug_kb": ("特权VIP.md",),
    },
    "noble": {
        "documents": ("贵族.md",),
        "testcase_kb": ("贵族.md",),
        "bug_kb": ("贵族.md",),
    },
    "wealth": {
        "documents": ("财富魅力等级.md",),
        "testcase_kb": ("财富等级.md",),
        "bug_kb": ("其他.md",),
    },
    "auth_login": {
        "documents": ("登录注册.md", "账号安全.md"),
        "testcase_kb": ("注册登录.md",),
        "bug_kb": ("注册登录.md",),
    },
    "face_auth": {
        "documents": ("真人认证.md",),
        "testcase_kb": ("人脸认证.md",),
        "bug_kb": ("人脸认证.md",),
    },
    "coin": {
        "documents": ("币商.md",),
        "testcase_kb": ("充值提现转账.md", "币商.md"),
        "bug_kb": ("充值提现转账.md",),
    },
    "agency": {
        "documents": ("Agency/",),
        "testcase_kb": ("公会.md",),
        "bug_kb": ("公会.md",),
    },
    "customer_service": {
        "documents": ("客服.md", "新用户与客服建联.md"),
        "testcase_kb": ("客服.md",),
        "bug_kb": ("客服.md",),
    },
    "super_admin": {
        "documents": ("超管操作.md",),
        "testcase_kb": ("超管.md",),
        "bug_kb": ("超管.md",),
    },
    "game": {
        "testcase_kb": ("游戏.md",),
        "bug_kb": ("游戏.md",),
    },
    "profile": {
        "documents": ("visitor.md",),
        "testcase_kb": ("个人主页.md",),
        "bug_kb": ("个人主页.md",),
    },
    "cp": {
        "documents": ("cp好友关系.md",),
        "testcase_kb": ("CP好友关系.md",),
        "bug_kb": ("其他.md",),
    },
    "dress": {
        "testcase_kb": ("装扮.md",),
        "bug_kb": ("其他.md",),
    },
    "mystery": {
        "testcase_kb": ("神秘人.md",),
        "bug_kb": ("其他.md",),
    },
    "collector": {
        "testcase_kb": ("收藏展馆.md",),
        "bug_kb": ("其他.md",),
    },
}

# prd-kb 模块文件名与 testcase-kb 对齐
MODULE_FILES = {
    k: ({**v, "prd_kb": v["testcase_kb"]} if "testcase_kb" in v else v)
    for k, v in MODULE_FILES.items()
}

DIR_KIND = {
    "documents": ROOT / "documents",
    "testcase_kb": ROOT / "testcase-kb",
    "prd_kb": ROOT / "prd-kb",
    "bug_kb": ROOT / "bug-kb",
    "templates": ROOT / "templates",
}

# templates 条目为 "**/" 或 "@all/" 时，递归收录该目录下全部 .md
TEMPLATES_ALL_MARKERS = frozenset({"**/", "@all/"})


def iter_template_markdown(base: Path | None = None) -> list[Path]:
    root = base or DIR_KIND["templates"]
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.md") if p.is_file())


def score_template_relevance(path: Path, queries: list[str]) -> int:
    """按文件名/相对路径与查询词的匹配度打分，供活动模板推荐排序。"""
    templates_root = DIR_KIND["templates"]
    try:
        rel = path.relative_to(templates_root)
    except ValueError:
        rel = path
    haystack = f"{rel} {path.stem}".lower()
    score = 0
    for raw in queries:
        q = raw.strip().lower()
        if not q or len(q) < 2:
            continue
        if q in haystack:
            score += 10
        for token in re.split(r"[\s_\-/]+", q):
            if len(token) >= 2 and token in haystack:
                score += 3
    return score


def match_module_keys(text: str) -> list[str]:
    lowered = text.lower()
    hits: list[str] = []
    for key, keywords in MODULE_KEYWORDS.items():
        if any(kw.lower() in lowered or kw in text for kw in keywords):
            hits.append(key)
    return hits


def resolve_hits(keys: list[str], *, version: bool = False) -> list[KbHit]:
    seen: set[str] = set()
    out: list[KbHit] = []
    for key in keys:
        spec = MODULE_FILES.get(key)
        if not spec:
            continue
        for kind, names in spec.items():
            base = DIR_KIND[kind]
            for name in names:
                if kind == "templates" and name in TEMPLATES_ALL_MARKERS:
                    for path in iter_template_markdown(base):
                        tag = str(path)
                        if tag in seen:
                            continue
                        seen.add(tag)
                        try:
                            rel = path.relative_to(base)
                        except ValueError:
                            rel = path
                        if len(rel.parts) == 1:
                            note = "通用模块模板"
                        else:
                            note = "历史活动参考"
                        out.append(KbHit(kind=kind, path=path, note=note))
                    continue
                if name.endswith("/"):
                    path = base / name.rstrip("/")
                    tag = f"{kind}:{key}"
                    if tag in seen:
                        continue
                    seen.add(tag)
                    note = "目录" if path.is_dir() else "目录（缺失）"
                    out.append(KbHit(kind=kind, path=path, note=note))
                    continue
                path = base / name
                tag = str(path)
                if tag in seen:
                    continue
                seen.add(tag)
                note = "存在" if path.is_file() or path.is_dir() else "缺失"
                out.append(KbHit(kind=kind, path=path, note=note))
    return out
