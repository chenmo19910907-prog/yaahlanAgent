#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将神秘人、VIP、贵族、财富等级、收藏展馆、CP好友关系、个人主页等独立功能从各父模块知识库拆出为单独 md。

输出：特权VIP.md、神秘人.md、贵族.md、财富等级.md、收藏展馆.md、CP好友关系.md、个人主页.md、装扮.md
其余用例仍保留在原父模块文件中。
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

ROOT = Path(__file__).resolve().parent.parent / "documents" / "documents"
SCRIPTS = Path(__file__).resolve().parent

VIP_MD = "特权VIP.md"

AUTH_LOGIN_MD = "注册登录.md"
CP_RELATIONSHIP_MD = "CP好友关系.md"
PROFILE_HOME_MD = "个人主页.md"
OUTFIT_MD = "装扮.md"

FEATURE_FILES = frozenset(
    {
        "神秘人.md",
        VIP_MD,
        "贵族.md",
        "财富等级.md",
        "收藏展馆.md",
        AUTH_LOGIN_MD,
        CP_RELATIONSHIP_MD,
        PROFILE_HOME_MD,
        OUTFIT_MD,
    },
)

PARENT_FILES = frozenset(
    {
        "房间.md",
        "房间PK.md",
        "礼物.md",
        "消息.md",
        "币商.md",
        "家族.md",
        "主题房.md",
        "动态.md",
        "其他模块.md",
        "客服.md",
        "超管.md",
        "游戏.md",
        "公会.md",
        "榜单与活动.md",
        "人脸认证.md",
    },
)

DOT_SHEET_RE = re.compile(r"^([^·]+)·(.+)$")

# 版本合订 / 多需求混排 Sheet（整表弱相关，不拆独立库）
SHEET_COMPOSITE_WEAK_RE = re.compile(r"&")

GENERIC_WEAK_LEAF_RE = re.compile(
    r"^优化需求$|^未归类需求$|^优化$|^技术优化$|^小需求$",
    re.I,
)

# 业务域已明确时，不因正文偶现 VIP9/VIP10 等抽入 VIP 库
VIP_EXCLUDE_PARENTS = frozenset(
    {
        "room",
        "room_pk",
        "gift",
        "coin",
        "family",
        "moments",
        "theme_room",
        "game",
        "agency",
        "rank_activity",
        "face_auth",
    }
)

VIP_CORE_SHEET_RE = re.compile(
    r"VIP\d+|VIP成长|VIP信息|VIP专属|vip体验|vip客服|"
    r"开通VIP|新增VIP\d|实时更新VIP|贵族与VIP|"
    r"vip成长值|VIP等级|VIP特权|"
    r"定制头像框|自定义座驾|定制座驾",
    re.I,
)

VIP_SHEET_WEAK_RE = re.compile(
    r"礼物展馆优化|心愿礼物|房间等级|麦位样式|平台标签|国家勋章|&",
    re.I,
)

# VIP 专属特权（优先于收藏展馆/礼物域）
VIP_PRIVILEGE_RE = re.compile(
    r"定制头像框|自定义座驾|定制座驾",
    re.I,
)

# 收藏展馆：仅强相关拆出；弱相关（平台 标签、国家勋章、版本合订 Sheet 等）留原父模块
EXHIBITION_PATH_SEGMENT = "勋章与展馆"

EXHIBITION_LEAF_STRONG_RE = re.compile(
    r"^成就收藏$|^礼物收集挑战$|^礼物展馆$|^道具展馆$|^珍宝展馆$|"
    r"^收藏展馆|^展馆优化$|^展馆锁定$|^勋章页外显$|^礼物展馆优化$|"
    r"勋章\+勋章优化|收藏展馆增加",
    re.I,
)

EXHIBITION_SHEET_WEAK_RE = re.compile(
    r"平台标签|国家勋章|·贵族$|新增VIP|VIP\d|礼物服务迁移|"
    r"个人数据请求|个人页红点|未归类需求|优化需求$|"
    r"送礼调用redis|标签调整|主题房活动|心愿礼物|房间等级|麦位样式|&",
    re.I,
)

MYSTERY_LEAF_STRONG_RE = re.compile(
    r"^神秘人身份$|^神秘人特权页$|^神秘人资料卡$|^神秘人语音变声$|"
    r"神秘人特权|神秘人身份|神秘人资料卡|神秘人语音变声",
    re.I,
)

MYSTERY_SHEET_WEAK_RE = re.compile(
    r"封禁踢出|充值轻度|改名卡|团战PK|真心话|榜单调整|商城新增|"
    r"返回顶部|房内礼物|欢迎消息|收听.*语音|歌曲列表|道具cdn|"
    r"关系改版|Android技术|&",
    re.I,
)

NOBLE_PATH_SEGMENT = "贵族与VIP"

NOBLE_LEAF_STRONG_RE = re.compile(
    r"^贵族$|^贵族等级特权$|贵族特权|贵族礼物|贵族展示|贵族勋章",
    re.I,
)

NOBLE_SHEET_WEAK_RE = re.compile(
    r"勋章与展馆|优化需求$|未归类需求|拉黑优化|发言飘屏|"
    r"个人数据请求|域名替换|自定义表情|WEB充值|PK活动|"
    r"隐身设置|房间红包|客服系统回归|moment优化|提现与转账|&",
    re.I,
)

WEALTH_LEAF_STRONG_RE = re.compile(
    r"财富等级改版|^财富等级$|^魅力等级$|财富魅力|等级进度|"
    r"房间成员等级|成员.*财富.*等级",
    re.I,
)

AUTH_LOGIN_PATH_SEGMENT = "账号与注册"

AUTH_LOGIN_LEAF_STRONG_RE = re.compile(
    r"^登录UI|^登录新增|^注销账号|^设置about|"
    r"^账号绑定|^账号密码|^重复输入区号|^新用户欢迎|"
    r"注册登录|测试账号送礼",
    re.I,
)

# 个人主页/资料编辑：与注册登录拆分，资料修改归入个人主页库
AUTH_LOGIN_PROFILE_EXCLUDE_RE = re.compile(
    r"profile|个人主页|个人资料|资料页|资料编辑|编辑资料|修改资料|"
    r"个人信息页|注册资料简化|谁看过我|靓号|资料页背景|资料座驾",
    re.I,
)

PROFILE_HOME_SHEET_STRONG_RE = re.compile(
    r"profile页|个人主页|个人资料|资料页|资料编辑|编辑资料|修改资料|"
    r"个人信息页|注册资料简化|profile页UI|资料页背景|"
    r"编辑个人资料|靓号设计|修改资料页|ios个人主页|个人资料修改",
    re.I,
)

PROFILE_HOME_SHEET_WEAK_RE = re.compile(
    r"好友申请|转发消息|用户关系迁移|关系改版|CP空间|"
    r"神秘人资料卡|仅.*跳转.*profile",
    re.I,
)

PROFILE_HOME_LEAF_STRONG_RE = re.compile(
    r"profile页|个人主页|个人资料|资料页|资料编辑|编辑资料|修改资料|"
    r"个人信息页|注册资料简化|profile页UI|资料页背景|"
    r"编辑个人资料|靓号|修改资料页|个人资料修改|资料座驾|"
    r"谁看过我",
    re.I,
)

OUTFIT_SHEET_STRONG_RE = re.compile(
    r"装扮商城|我的装扮|装扮购买|装扮使用|装扮中心|装扮预览|"
    r"outfitstore|我的装扮UI|装扮商城入口|房间背包装扮|"
    r"送礼条|进房广播|上麦特效|入场特效|入场条|聊天气泡|"
    r"头像框.*tab|座驾.*tab|道具礼物",
    re.I,
)

OUTFIT_SHEET_WEAK_RE = re.compile(
    r"仅.*跳转.*装扮|个人资料修改靓号",
    re.I,
)

OUTFIT_LEAF_STRONG_RE = re.compile(
    r"装扮商城|我的装扮|装扮购买|装扮使用|装扮中心|装扮预览|"
    r"outfitstore|我的装扮UI|装扮商城入口|房间背包装扮|"
    r"送礼条|进房广播|上麦特效",
    re.I,
)

OUTFIT_MODULE_STRONG_RE = re.compile(
    r"装扮商城|我的装扮|装扮购买|装扮穿戴|装扮佩戴|装扮预览|"
    r"装扮展示|装扮为空|装扮更换|outfitstore|装扮中心|"
    r"去商城逛逛|佩戴|穿戴|取消佩戴",
    re.I,
)

PROFILE_HOME_MODULE_STRONG_RE = re.compile(
    r"编辑资料|修改资料|资料编辑|个人资料修改|个人资料查看|"
    r"资料页|profile|个人信息页|靓号|资料页背景|资料座驾|"
    r"个人资料页|编辑个人资料|修改资料页提醒|资料页背景装扮|"
    r"个人信息页修改资料提醒|修改资料页提醒|谁看过我",
    re.I,
)

AUTH_LOGIN_SHEET_WEAK_RE = re.compile(
    r"语音通话|幸运祈愿|自定义表情|活动分享|分区策略|个人数据|"
    r"谁看过我|拉黑|网络请求|接口接缓存|iOS我的页面|标签UI|"
    r"神秘人资料卡|财富等级|Android技术优化|主播成长|上麦时长|"
    r"支付验证|定制礼物|不跟版|^iOS$",
    re.I,
)

AUTH_LOGIN_PATH_LEAF_WEAK_RE = re.compile(
    r"语音通话|幸运祈愿|自定义表情|活动分享|分区策略|个人数据|"
    r"拉黑|网络请求|缓存|谁看过我|标签UI|支付验证",
    re.I,
)

WEALTH_SHEET_WEAK_RE = re.compile(
    r"家族等级|家族设置|加入家族|主题房活动|新增VIP|VIP\d|"
    r"乱斗PK|IM UI|聊天列表|红包与宝箱|房间宝箱|隐身设置|"
    r"moment优化|支付发布|礼物展馆优化|心愿礼物|麦位样式|&|"
    r"客服系统回归|语音房客服|入场条|标签UI|网络请求|封禁踢出",
    re.I,
)

CP_RELATIONSHIP_SHEET_STRONG_RE = re.compile(
    r"关系改版|关系链·关系改版|面板与送礼·关系改版|"
    r"新增关系外显|送CP头像礼物|麦位·新增关系外显|"
    r"私聊与群聊·关系改版",
    re.I,
)

CP_RELATIONSHIP_SHEET_WEAK_RE = re.compile(
    r"用户关系迁移|后台设备拉黑|CP摩天轮|CP房PK|"
    r"好友申请|转发消息|iOS我的页面网络|好友关系部分|&",
    re.I,
)

CP_RELATIONSHIP_LEAF_STRONG_RE = re.compile(
    r"^关系改版|^关系特权|^关系空间|^关系外显|"
    r"亲密空间|CP空间|CP连线|CP UI|CP交互|CP 页面|"
    r"组成关系|组建关系|关系入口|加关系值|解除关系|"
    r"cp关系关系外显|CP空间送礼|主态空间|"
    r"客态.*关系空间|组成关系弹窗|组成关系广播|"
    r"关系特权页面|CPbanner|快捷礼物-CP|"
    r"^关系$|我的关系|入口二.*我的关系|"
    r"LV\d+\(\d+个权益\)|CP模式下|隐藏关系|"
    r"非房间内礼物面板送CP",
    re.I,
)

CP_RELATIONSHIP_MODULE_STRONG_RE = re.compile(
    r"关系特权|关系空间|亲密空间|CP空间|CP连线|"
    r"组成关系|组建关系|关系外显|亲密度升级|"
    r"关系等级|衰减保级|CP双方|COUPLE|BUDDY|"
    r"组成关系广播|更多按钮-解除关系|加关系值|"
    r"CP空间送礼|CP空间礼物|祝福按钮|祝福记录|"
    r"CP特权|好友特权",
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


def parse_sheet_parts(sheet: str) -> Tuple[str, str]:
    m = DOT_SHEET_RE.match((sheet or "").strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", (sheet or "未归类需求").strip()


def _title_blob(sheet: str, module: str) -> str:
    return csm._title_blob(sheet, module)


def should_extract_vip(block: CaseBlock) -> bool:
    """仅 Sheet/路径以 VIP 能力为主时拆入 特权VIP.md；合订需求与业务域内 VIP 提及保留父模块。"""
    parent = csm.classify_target(block)
    if parent in VIP_EXCLUDE_PARENTS:
        return False
    sheet = (block.sheet or "").strip()
    module = (block.module or "").strip()
    if not sheet or VIP_SHEET_WEAK_RE.search(sheet) or SHEET_COMPOSITE_WEAK_RE.search(sheet):
        return False
    if VIP_CORE_SHEET_RE.search(sheet):
        return True
    leaf = _sheet_leaf(sheet)
    if GENERIC_WEAK_LEAF_RE.search(leaf):
        return False
    if VIP_CORE_SHEET_RE.search(module) and (
        NOBLE_PATH_SEGMENT in sheet.split("·")
        or re.search(r"(?:^|·)VIP(?:·|$)", sheet, re.I)
    ):
        return True
    return False


def _sheet_leaf(sheet: str) -> str:
    parts = [p.strip() for p in (sheet or "").split("·") if p.strip()]
    return parts[-1] if parts else ""


def _sheet_has_exhibition_path(sheet: str) -> bool:
    return EXHIBITION_PATH_SEGMENT in (sheet or "").split("·")


def should_extract_exhibition(block: CaseBlock) -> bool:
    """仅强相关（展馆/成就收藏/礼物收集挑战本体）拆入收藏展馆.md。"""
    sheet_mod = f"{block.sheet or ''} {block.module or ''}"
    if VIP_PRIVILEGE_RE.search(sheet_mod):
        return False
    sheet = (block.sheet or "").strip()
    if not sheet or EXHIBITION_SHEET_WEAK_RE.search(sheet):
        return False

    leaf = _sheet_leaf(sheet)
    if not leaf or not EXHIBITION_LEAF_STRONG_RE.search(leaf):
        return False

    if _sheet_has_exhibition_path(sheet):
        return True

    # 非「勋章与展馆」路径：仅叶子标题即展馆核心能力时拆出
    if re.search(
        r"^成就收藏$|^礼物收集挑战$|^礼物展馆$|^道具展馆$|^珍宝展馆$|^收藏展馆",
        leaf,
        re.I,
    ):
        return True
    return False


def should_extract_mystery(block: CaseBlock) -> bool:
    """神秘人身份/特权页/资料卡/语音变声等强相关才拆出。"""
    sheet = (block.sheet or "").strip()
    if not sheet or MYSTERY_SHEET_WEAK_RE.search(sheet) or SHEET_COMPOSITE_WEAK_RE.search(sheet):
        return False
    leaf = _sheet_leaf(sheet)
    if GENERIC_WEAK_LEAF_RE.search(leaf):
        return False
    if MYSTERY_LEAF_STRONG_RE.search(leaf):
        return True
    if "神秘人" in sheet.split("·") and MYSTERY_LEAF_STRONG_RE.search(sheet):
        return True
    return False


def should_extract_noble(block: CaseBlock) -> bool:
    """贵族等级/特权本体强相关才拆出；展馆·贵族、房间杂项优化等留父模块。"""
    sheet_mod = f"{block.sheet or ''} {block.module or ''}"
    if VIP_PRIVILEGE_RE.search(sheet_mod):
        return False
    sheet = (block.sheet or "").strip()
    if not sheet or NOBLE_SHEET_WEAK_RE.search(sheet) or SHEET_COMPOSITE_WEAK_RE.search(sheet):
        return False
    leaf = _sheet_leaf(sheet)
    if GENERIC_WEAK_LEAF_RE.search(leaf):
        return False
    if re.search(r"VIP\d|新增VIP|vip体验|vip客服", leaf, re.I):
        return False
    if NOBLE_LEAF_STRONG_RE.search(leaf) or leaf in ("贵族", "贵族等级特权"):
        return True
    if NOBLE_PATH_SEGMENT in sheet.split("·"):
        tail = sheet.split(NOBLE_PATH_SEGMENT, 1)[-1]
        if re.search(r"贵族等级|贵族特权|^贵族", tail, re.I) and not re.search(
            r"VIP\d|新增VIP", tail, re.I
        ):
            return True
    return False


def should_extract_auth_login(block: CaseBlock) -> bool:
    """注册/登录/注销等强相关才拆入注册登录.md；个人主页/资料编辑不归入此库。"""
    sheet = (block.sheet or "").strip()
    module = (block.module or "").strip()
    if AUTH_LOGIN_PROFILE_EXCLUDE_RE.search(sheet) or AUTH_LOGIN_PROFILE_EXCLUDE_RE.search(
        module
    ):
        return False
    if not sheet or AUTH_LOGIN_SHEET_WEAK_RE.search(sheet) or SHEET_COMPOSITE_WEAK_RE.search(
        sheet
    ):
        return False
    leaf = _sheet_leaf(sheet)
    if GENERIC_WEAK_LEAF_RE.search(leaf):
        return False
    if AUTH_LOGIN_LEAF_STRONG_RE.search(leaf):
        return True
    if AUTH_LOGIN_PATH_SEGMENT in sheet.split("·"):
        if AUTH_LOGIN_PATH_LEAF_WEAK_RE.search(leaf):
            return False
        if AUTH_LOGIN_LEAF_STRONG_RE.search(leaf) or re.search(
            r"注册|登录|注销|账号绑定|账号密码|设置about|区号|欢迎",
            leaf,
            re.I,
        ):
            return True
        return False
    if re.search(r"^注册|^登录|注销账号|设置about", sheet, re.I):
        return True
    return False


def should_extract_outfit(block: CaseBlock) -> bool:
    """装扮商城、我的装扮、购买佩戴等强相关才拆入装扮.md。"""
    sheet = (block.sheet or "").strip()
    module = (block.module or "").strip()
    if not sheet and not module:
        return False
    if OUTFIT_SHEET_WEAK_RE.search(sheet) and not OUTFIT_MODULE_STRONG_RE.search(module):
        return False
    if OUTFIT_SHEET_STRONG_RE.search(sheet):
        return True
    leaf = _sheet_leaf(sheet)
    if OUTFIT_LEAF_STRONG_RE.search(leaf):
        return True
    if OUTFIT_MODULE_STRONG_RE.search(module):
        return True
    if re.search(r"装扮商城|我的装扮|outfitstore|装扮购买|装扮佩戴", sheet, re.I):
        return True
    return False


def should_extract_profile_home(block: CaseBlock) -> bool:
    """个人主页、资料页、资料编辑/修改等强相关才拆入个人主页.md。"""
    sheet = (block.sheet or "").strip()
    module = (block.module or "").strip()
    if not sheet and not module:
        return False
    if PROFILE_HOME_SHEET_WEAK_RE.search(sheet) and not PROFILE_HOME_MODULE_STRONG_RE.search(
        module
    ):
        return False
    if PROFILE_HOME_SHEET_STRONG_RE.search(sheet):
        return True
    leaf = _sheet_leaf(sheet)
    if PROFILE_HOME_LEAF_STRONG_RE.search(leaf):
        return True
    if PROFILE_HOME_MODULE_STRONG_RE.search(module):
        return True
    if re.search(r"profile|个人主页|个人资料|资料编辑|编辑资料|修改资料", sheet, re.I):
        return True
    return False


def should_extract_wealth(block: CaseBlock) -> bool:
    """财富/魅力等级改版等强相关才拆出；家族等级、IM/房间合订等留父模块。"""
    sheet = (block.sheet or "").strip()
    if not sheet or WEALTH_SHEET_WEAK_RE.search(sheet) or SHEET_COMPOSITE_WEAK_RE.search(sheet):
        return False
    leaf = _sheet_leaf(sheet)
    if GENERIC_WEAK_LEAF_RE.search(leaf):
        return False
    return bool(WEALTH_LEAF_STRONG_RE.search(leaf))


def should_extract_cp_relationship(block: CaseBlock) -> bool:
    """CP/好友关系、亲密度、关系空间等强相关才拆出；关系迁移/好友申请等留父模块。"""
    sheet = (block.sheet or "").strip()
    module = (block.module or "").strip()
    if not sheet:
        return False
    if re.search(r"用户关系迁移|好友申请优化|转发消息", sheet, re.I):
        return False
    if re.search(r"^后台设备拉黑$", _sheet_leaf(sheet), re.I) and not CP_RELATIONSHIP_MODULE_STRONG_RE.search(
        module
    ):
        return False
    if CP_RELATIONSHIP_SHEET_WEAK_RE.search(sheet) and not CP_RELATIONSHIP_MODULE_STRONG_RE.search(
        module
    ):
        return False
    if SHEET_COMPOSITE_WEAK_RE.search(sheet) and not CP_RELATIONSHIP_MODULE_STRONG_RE.search(
        module
    ):
        return False
    leaf = _sheet_leaf(sheet)
    if GENERIC_WEAK_LEAF_RE.search(leaf) and not CP_RELATIONSHIP_MODULE_STRONG_RE.search(module):
        return False
    if CP_RELATIONSHIP_SHEET_STRONG_RE.search(sheet):
        return True
    if CP_RELATIONSHIP_LEAF_STRONG_RE.search(leaf):
        return True
    if CP_RELATIONSHIP_MODULE_STRONG_RE.search(module):
        return True
    if "关系链" in sheet.split("·") and re.search(r"关系改版|关系外显", sheet, re.I):
        return True
    return False


def classify_feature(block: CaseBlock) -> Optional[str]:
    """独立功能库：仅强相关拆出，弱相关由 classify_target 保留在父业务域。"""
    sheet_mod = f"{block.sheet or ''} {block.module or ''}"
    if should_extract_outfit(block):
        return OUTFIT_MD
    if should_extract_profile_home(block):
        return PROFILE_HOME_MD
    if VIP_PRIVILEGE_RE.search(sheet_mod):
        return VIP_MD
    if should_extract_vip(block):
        return VIP_MD
    if should_extract_exhibition(block):
        return "收藏展馆.md"
    if should_extract_auth_login(block):
        return AUTH_LOGIN_MD
    if should_extract_mystery(block):
        return "神秘人.md"
    if should_extract_noble(block):
        return "贵族.md"
    if should_extract_wealth(block):
        return "财富等级.md"
    if should_extract_cp_relationship(block):
        return CP_RELATIONSHIP_MD
    return None


def normalize_feature_sheet(origin_parent: str, block: CaseBlock, feat: str) -> str:
    """功能库内 Sheet 名：带来源父模块，避免冲突。"""
    parent = origin_parent.replace(".md", "")
    sub, inner = parse_sheet_parts(block.sheet or "")
    feat_label = feat.replace(".md", "")

    if feat == OUTFIT_MD:
        base = (block.sheet or "").strip() or "未归类需求"
        if base.startswith(f"{parent}·"):
            base = base[len(parent) + 1 :]
        parts = [p.strip() for p in base.split("·") if p.strip()]
        parent_domains = (
            "消息",
            "礼物",
            "超管",
            "榜单与活动",
            "房间",
            "其他模块",
            "币商",
            "主题房",
            "动态",
            "客服",
            "游戏",
            "公会",
            "人脸认证",
            "房间PK",
            "注册登录",
            "个人主页",
            "特权VIP",
            "收藏展馆",
            "贵族",
            "财富等级",
            "CP好友关系",
        )
        if parts and parts[0] in parent_domains:
            parts = parts[1:]
        base = "·".join(parts) if parts else "未归类需求"
        if OUTFIT_MODULE_STRONG_RE.search(block.module or ""):
            mod = (block.module or "").strip()
            if mod:
                return f"装扮·{mod}"
        if not base.startswith("装扮"):
            return f"装扮·{base}" if base != "未归类需求" else "装扮"
        return base

    if feat == PROFILE_HOME_MD:
        base = (block.sheet or "").strip() or "未归类需求"
        if base.startswith(f"{parent}·"):
            base = base[len(parent) + 1 :]
        parts = [p.strip() for p in base.split("·") if p.strip()]
        parent_domains = (
            "消息",
            "礼物",
            "超管",
            "榜单与活动",
            "房间",
            "其他模块",
            "币商",
            "主题房",
            "动态",
            "客服",
            "游戏",
            "公会",
            "人脸认证",
            "房间PK",
            "注册登录",
        )
        if parts and parts[0] in parent_domains:
            parts = parts[1:]
        base = "·".join(parts) if parts else "未归类需求"
        if PROFILE_HOME_MODULE_STRONG_RE.search(block.module or ""):
            mod = (block.module or "").strip()
            if mod:
                return f"个人主页·{mod}"
        if not base.startswith("个人主页"):
            return f"个人主页·{base}" if base != "未归类需求" else "个人主页"
        return base

    if feat == CP_RELATIONSHIP_MD:
        base = (block.sheet or "").strip() or "未归类需求"
        if base.startswith(f"{parent}·"):
            base = base[len(parent) + 1 :]
        parts = [p.strip() for p in base.split("·") if p.strip()]
        parent_domains = (
            "消息",
            "礼物",
            "超管",
            "榜单与活动",
            "房间",
            "其他模块",
            "币商",
            "主题房",
            "动态",
            "客服",
            "游戏",
            "公会",
            "人脸认证",
            "房间PK",
        )
        if parts and parts[0] in parent_domains:
            parts = parts[1:]
        base = "·".join(parts) if parts else "未归类需求"
        if re.search(r"redis|后台设备拉黑", base, re.I) and CP_RELATIONSHIP_MODULE_STRONG_RE.search(
            block.module or ""
        ):
            mod = (block.module or "").strip()
            if mod:
                return f"CP好友关系·{mod}"
        if not base.startswith("CP好友关系"):
            return f"CP好友关系·{base}" if base != "未归类需求" else "CP好友关系"
        return base

    if sub in (
        feat_label,
        "神秘人",
        "贵族与VIP",
        "贵族",
        "收藏展馆",
        "注册登录",
        "CP好友关系",
        "个人主页",
        "装扮",
    ):
        base = inner or sub
    else:
        base = block.sheet or "未归类需求"
    if base.startswith(f"{parent}·"):
        return base
    return f"{parent}·{base}"


def load_all(root: Path) -> List[Tuple[CaseBlock, str]]:
    """(block, origin_parent_file)"""
    out: List[Tuple[CaseBlock, str]] = []
    for p in sorted(root.glob("*.md")):
        if p.name.startswith("_") or p.name.lower() == "readme.md":
            continue
        if p.name not in PARENT_FILES and p.name not in FEATURE_FILES:
            continue
        for b in extract_blocks(p.read_text(encoding="utf-8")):
            out.append((b, p.name))
    return out


def pick_latest(
    tagged: List[Tuple[CaseBlock, str, str]],
) -> Dict[Tuple[str, str, str], CaseBlock]:
    best: Dict[Tuple[str, str, str], CaseBlock] = {}
    for b, target, sheet in tagged:
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


def kb_file_sort_key(fname: str) -> tuple:
    """特权VIP.md 置顶；其余 _ 前缀元数据次之；再按文件名排序。"""
    if fname == VIP_MD:
        return (0, fname)
    if fname.startswith("_"):
        return (1, fname)
    return (2, fname)


def main() -> None:
    ap = argparse.ArgumentParser(description="拆出独立功能知识库")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root: Path = args.root

    raw = load_all(root)
    tagged: List[Tuple[CaseBlock, str, str]] = []
    stats: Dict[str, int] = defaultdict(int)

    for b, origin in raw:
        feat = classify_feature(b)
        if feat:
            target = feat
            sheet = normalize_feature_sheet(origin, b, feat)
            stats[feat] += 1
        else:
            if origin in FEATURE_FILES:
                # 已不再属于功能域 → 落回礼物（按 classify_target）
                parent = csm.classify_target(b)
                parent_map = {
                    "room": "房间.md",
                    "gift": "礼物.md",
                    "message": "消息.md",
                    "coin": "币商.md",
                    "family": "家族.md",
                    "theme_room": "主题房.md",
                    "moments": "动态.md",
                    "other": "其他模块.md",
                    "customer_service": "客服.md",
                    "super_admin": "超管.md",
                    "room_pk": "房间PK.md",
                    "game": "游戏.md",
                    "agency": "公会.md",
                    "rank_activity": "榜单与活动.md",
                    "face_auth": "人脸认证.md",
                    "auth_login": AUTH_LOGIN_MD,
                }
                target = parent_map.get(parent, "其他模块.md")
            else:
                target = origin
            sheet = b.sheet or "未归类需求"
        tagged.append((b, target, sheet))

    latest = pick_latest(tagged)
    trees = build_trees(latest)

    print(f"输出 {len(trees)} 个文件")
    for feat in sorted(FEATURE_FILES):
        if feat in trees:
            n = sum(len(c) for c in trees[feat].values())
            print(f"  {feat}: {n} 模块 (抽取 {stats.get(feat, 0)} 块)")
    for fk in sorted(trees.keys()):
        if fk not in FEATURE_FILES:
            n = sum(len(c) for c in trees[fk].values())
            if fk in PARENT_FILES:
                print(f"  {fk}: {n} 模块 (保留)")

    if args.dry_run:
        return

    written: Set[str] = set()
    intros = {
        "神秘人.md": "> **范围**：神秘人身份、特权页、资料卡、语音变声等强相关能力。\n",
        VIP_MD: "> **范围**：特权 VIP 等级、成长值、专属特权、定制头像框/座驾、VIP 客服等。\n",
        "贵族.md": "> **范围**：贵族等级、特权、贵族礼物与展示等强相关能力。\n",
        "财富等级.md": "> **范围**：财富/魅力等级、等级改版与进度等强相关能力。\n",
        "收藏展馆.md": "> **范围**：收藏展馆、礼物展馆、道具展馆、成就收藏、礼物收集挑战等强相关能力（弱相关仍留各父模块）。\n",
        AUTH_LOGIN_MD: "> **范围**：注册、登录、注销、账号绑定、密码与白名单等强相关能力。\n",
        CP_RELATIONSHIP_MD: (
            "> **范围**：CP/好友关系、亲密度、关系空间、关系特权、关系外显、"
            "组建/解除关系等强相关能力（弱相关仍留各父模块）。\n"
        ),
        PROFILE_HOME_MD: (
            "> **范围**：个人主页（profile）、资料页、资料编辑/修改、靓号、"
            "资料页背景、谁看过我等强相关能力。\n"
        ),
        OUTFIT_MD: (
            "> **范围**：装扮商城、我的装扮、装扮购买与佩戴/使用、"
            "头像框/座驾/入场条/聊天气泡等装扮道具。\n"
        ),
    }

    for fk, sheets_map in trees.items():
        title = "特权VIP" if fk == VIP_MD else fk.replace(".md", "")
        md = csm.build_from_tree(title, sheets_map)
        if fk in intros and md.startswith(f"# "):
            rest = md.split("\n---\n\n", 1)
            body = rest[-1] if len(rest) > 1 else md
            if body.lstrip().startswith(f"# {title}"):
                body = body.split("\n", 1)[1]
            md = f"# {title}\n\n{intros[fk]}\n---\n\n" + body.lstrip("\n")
        if fk == "房间PK.md":
            intro = "# 房间PK\n\n> **范围**：房间 PK / 跨房 PK。\n\n---\n\n"
            if md.startswith("# 房间PK"):
                rest = md.split("\n---\n\n", 1)
                body = rest[-1] if len(rest) > 1 else md
                if body.lstrip().startswith("# 房间PK"):
                    body = body.split("\n", 1)[1]
                md = intro + body.lstrip("\n")
        (root / fk).write_text(md, encoding="utf-8")
        written.add(fk)

    keep = written | {"README.md"}
    for p in root.glob("*.md"):
        if p.name not in keep and not p.name.startswith("_"):
            p.unlink()

    opt = SCRIPTS / "optimize_kb_docs.py"
    if opt.exists():
        subprocess.run(
            [sys.executable, str(opt), "--root", str(root)],
            check=False,
        )

    print(f"extract-features done -> {root}")


if __name__ == "__main__":
    main()
