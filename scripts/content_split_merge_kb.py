#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按语义对 testcase-kb 知识库做「拆分 + 合并」：

拆分：将误归入某大模块的用例块，按 Sheet/模块/正文关键词重新归类到正确 md。
合并：同一 Sheet 下语义相近的 ### 功能模块合并为一个章节，子模块保留为 #### 变体。

依赖：content_optimize_kb_docs.py 的解析与渲染能力。
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent / "testcase-kb"

# 加载 content_optimize_kb_docs
_SPEC = importlib.util.spec_from_file_location(
    "content_opt",
    Path(__file__).parent / "content_optimize_kb_docs.py",
)
content_opt = importlib.util.module_from_spec(_SPEC)
sys.modules["content_opt"] = content_opt
assert _SPEC.loader is not None
_SPEC.loader.exec_module(content_opt)

CaseBlock = content_opt.CaseBlock
extract_blocks = content_opt.extract_blocks
build_document = content_opt.build_document
SAME_AS_SUFFIX_RE = content_opt.SAME_AS_SUFFIX_RE

KB_FILE_NAMES: Dict[str, str] = {
    "room_pk": "房间PK.md",
    "room": "房间.md",
    "gift": "礼物.md",
    "family": "家族.md",
    "theme_room": "主题房.md",
    "moments": "动态.md",
    "message": "消息.md",
    "face_auth": "人脸认证.md",
    "auth_login": "注册登录.md",
    "customer_service": "客服.md",
    "super_admin": "超管.md",
    "agency": "公会.md",
    "coin": "币商.md",
    "game": "游戏.md",
    "rank": "榜单.md",
    "activity": "活动.md",
}

DEFAULT_FALLBACK_TARGET = "room"

# 版本合订 xlsx 中 Sheet 名泛化、需靠模块名二次路由
WEAK_AGGREGATE_SHEET_RE = re.compile(
    r"^优化(?:部分|需求|点|功能|逻辑)|^未归类需求$|^新增需求$|^优化点需求$",
    re.I,
)

def _title_blob(sheet: str, module: str) -> str:
    """Sheet / 子域·Sheet / 模块名合并，用于按标题判定业务域。"""
    parts: List[str] = [sheet or "", module or ""]
    if "·" in (sheet or ""):
        parts.extend((sheet or "").split("·"))
    return " ".join(p.strip() for p in parts if p.strip())


def _sheet_leaf(sheet: str) -> str:
    parts = [p.strip() for p in (sheet or "").split("·") if p.strip()]
    return parts[-1] if parts else (sheet or "").strip()


# Sheet/模块标题优先（高于正文宽泛关键词，避免混合 xlsx 误划入礼物）
TITLE_DOMAIN_RULES: List[Tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"VIP成长|vip页面|购买tab信息与充值tab|新增VIP\d|贵族与VIP|"
            r"新用户vip体验",
            re.I,
        ),
        "coin",
    ),
    (re.compile(r"app图标|启动器图标|图标更换", re.I), "room"),
    (re.compile(r"iOS真人认证|未成年警告", re.I), "face_auth"),
    (re.compile(r"发言飘屏", re.I), "room"),
    (re.compile(r"礼物播放器", re.I), "gift"),
    (re.compile(r"游戏bridge|游戏客服", re.I), "game"),
    (re.compile(r"活动大入口|内嵌web", re.I), "activity"),
    (re.compile(r"房间管理员权限", re.I), "room"),
    (re.compile(r"自定义接收通知", re.I), "message"),
    (re.compile(r"^支付验证|^支付验证重构", re.I), "auth_login"),
    (
        re.compile(
            r"语音通话优化|语音通话接入|火山引擎|分区策略·语音通话|"
            r"私聊与群聊·语音通话|账号与注册·语音通话",
            re.I,
        ),
        "message",
    ),
    (re.compile(r"网络速度检测|网络速度|网速", re.I), "room"),
    (re.compile(
        r"网络请求优化|接口接缓存|首页懒加载|Android回退|回退\s*SDK|"
        r"iOS我的页面|安卓普通麦位|UIScene|lifecycle",
        re.I,
    ), "room"),
    (re.compile(r"钻石充值明细|钻石明细筛选|钻石明细|钻石补偿", re.I), "coin"),
    (re.compile(r"审核后台|设备拉黑|历史设备", re.I), "super_admin"),
    (re.compile(r"域名替换", re.I), "coin"),
    (re.compile(r"广播分流", re.I), "room"),
    (re.compile(
        r"麦位系统|语音房麦位|付费表情|房间列表边框|心愿礼物下线|"
        r"房间等级5|环绕模式|20麦位",
        re.I,
    ), "room"),
    (re.compile(r"跨房\s*PK|跨房PK|跨房PK分区|PK分区策略", re.I), "room_pk"),
    (re.compile(r"关系改版|亲密度|关系空间|组成关系", re.I), "message"),
    (re.compile(r"私聊与群聊·.*设置页ui|IM·.*设置页", re.I), "message"),
    (re.compile(r"主播薪资|预提|公会长|公会预提|修改公会长", re.I), "agency"),
    (re.compile(r"个人数据请求|新用户承接", re.I), "agency"),
    (re.compile(r"^Redis迁移", re.I), "room"),
    (re.compile(r"首充弹窗", re.I), "coin"),
    (re.compile(r"改名卡", re.I), "message"),
    (re.compile(r"定制礼物违规|定制礼物", re.I), "gift"),
    (re.compile(r"平台标签调整", re.I), "gift"),
    (re.compile(r"每日任务改版|每日任务", re.I), "activity"),
    (re.compile(r"房间小时榜|房间操作优化", re.I), "room"),
    (re.compile(r"^客服后台$|^客服评价$|访客记录剔除客服", re.I), "customer_service"),
]

# Sheet 路径中含其它业务域前缀时优先归位（高于 coin/公会 等宽泛 DOMAIN_ROUTING）
CROSS_DOMAIN_PREFIX_RULES: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"^支付验证|支付验证重构", re.I), "auth_login"),
    (re.compile(r"私聊与群聊·|^私聊与群聊$", re.I), "message"),
    (re.compile(r"面板与送礼·|礼物与打赏·|房内礼物·", re.I), "gift"),
    (re.compile(r"发布与浏览·", re.I), "moments"),
    (re.compile(r"提现与转账·cp头像|提现与转账·贵族|提现与转账·平台标签", re.I), "gift"),
    (re.compile(r"提现与转账·域名", re.I), "coin"),
    (re.compile(r"提现与转账·", re.I), "coin"),
    (
        re.compile(
            r"账号与注册·(?:支付验证|注册|登录|注销|绑定|密码|设置about|资料|区号)",
            re.I,
        ),
        "auth_login",
    ),
    (re.compile(r"账号与注册·", re.I), "auth_login"),
    (re.compile(r"进房·|麦位·|成员与等级·|服务端进房", re.I), "room"),
    (
        re.compile(
            r"^房间·|房间操作优化|房间小时榜|房间背景|房间管理员|"
            r"房间成员|房间收听|房间等级",
            re.I,
        ),
        "room",
    ),
    (re.compile(r"客服·|^客服后台$|^客服评价$", re.I), "customer_service"),
    (re.compile(r"超管·|审核·|审核后台", re.I), "super_admin"),
    (re.compile(r"主题房·|^主题房$", re.I), "theme_room"),
    (
        re.compile(
            r"家族·|^家族改版|创建与加入·|任务与等级·|成员管理·发言飘屏",
            re.I,
        ),
        "family",
    ),
    (
        re.compile(
            r"公会·|^公会|公会长|主播薪资|薪资预提|yaahlan-family|"
            r"yaahlan-star",
            re.I,
        ),
        "agency",
    ),
    (re.compile(r"游戏·|游戏bridge|游戏客服|概率游戏|大冒险", re.I), "game"),
    (re.compile(r"勋章与展馆·|礼物展馆|cp头像礼物", re.I), "gift"),
    (re.compile(r"提现与转账·贵族|·贵族$", re.I), "gift"),
    (re.compile(r"关系链·|关系改版|CP好友|组成关系", re.I), "message"),
    (re.compile(r"活动·主题房|主题房活动", re.I), "theme_room"),
    (re.compile(r"榜单与活动·", re.I), "activity"),
    (re.compile(r"活动运营·|^活动·", re.I), "activity"),
    (re.compile(r"个人数据请求|我的公会", re.I), "agency"),
    (re.compile(r"其他模块·礼物|iOS我的页面", re.I), "gift"),
    (re.compile(r"背包·每日任务", re.I), "gift"),
    (
        re.compile(
            r"首页懒加载|网络请求优化|接口接缓存|安卓.*接口接缓存|"
            r"安卓普通麦位|房间帧跳转|语音房跳转",
            re.I,
        ),
        "room",
    ),
    (re.compile(r"子公会.*退出母公会|退出母公会", re.I), "agency"),
    (re.compile(r"广播分流", re.I), "room"),
    (
        re.compile(r"界面与运营·(?!活动.*主题房|活动新增房间大入口)", re.I),
        "room",
    ),
]

# 从「其他模块」迁出：Sheet/标题含明确业务域关键词（优先于泛化 other 规则）
DOMAIN_ROUTING_RULES: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"主题房|活动房|活动·[^·]*主题房", re.I), "theme_room"),
    (re.compile(r"公会|公会长|工会长|预提黑名单|助理权限", re.I), "agency"),
    (
        re.compile(
            r"^家族|家族改版|创建与加入|成员管理|任务与等级|家族房|家族房间",
            re.I,
        ),
        "family",
    ),
    (
        re.compile(
            r"^币商|币商·|商户业务|充值·|提现与转账·|"
            r"^充值$|^提现$|^转账$|支付验证|钻石明细|"
            r"^首充|首充弹窗|钱包转账",
            re.I,
        ),
        "coin",
    ),
    (re.compile(r"发布与浏览|moment|动态·", re.I), "moments"),
    (
        re.compile(
            r"面板与送礼|礼物与打赏|背包|道具类型|我的装扮|商店UI|"
            r"房主学院|礼物服务",
            re.I,
        ),
        "gift",
    ),
    (
        re.compile(
            r"进房|麦位|成员与等级|界面与运营|房间·|安卓普通麦位|语音房|"
            r"服务端进房|入场条|红包与宝箱",
            re.I,
        ),
        "room",
    ),
    (
        re.compile(
            r"概率游戏|大冒险|gamebridge|足球大将|游戏客服",
            re.I,
        ),
        "game",
    ),
    (
        re.compile(
            r"榜单|排行榜|全服榜|打榜|揭榜|荣誉墙|榜种|room页榜单",
            re.I,
        ),
        "rank",
    ),
    (
        re.compile(
            r"活动条|摩天轮|年末盛典|活动运营|活动支持|活动·[^·]*活动(?!房)",
            re.I,
        ),
        "activity",
    ),
    (
        re.compile(
            r"IM·|私聊|群聊|好友申请|用户信息请求|首页改版|平台/主播任务",
            re.I,
        ),
        "message",
    ),
    (re.compile(r"^客服·|·客服·|客服下发|客服快捷|客服评价|客服系统|券包|快捷回复|帮助中心", re.I), "customer_service"),
    (re.compile(r"超管|审核·|审核后台|设备拉黑|后台新增|后台设备|用户关系迁移", re.I), "super_admin"),
    (
        re.compile(
            r"注册资料|登录UI|登录新增|注销账号|设置about|"
            r"账号绑定|账号密码|重复输入区号|新用户欢迎|注册登录|测试账号送礼",
            re.I,
        ),
        "auth_login",
    ),
    (re.compile(r"房间黑名单|房间信息页.*黑名单|黑名单人数上限", re.I), "room"),
    (re.compile(r"预提黑名单|公会.*黑名单", re.I), "agency"),
    (
        re.compile(
            r"退出账号|Log\s*out|黑名单|密码安全|设备安全|安全中心|谁看过我|设置页ui",
            re.I,
        ),
        "auth_login",
    ),
    (re.compile(r"真人认证|人脸认证", re.I), "face_auth"),
]

# 按功能模块名细分的域（优先于 Sheet 级「广播分流」等）
MODULE_DOMAIN_RULES: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"^游戏广播$", re.I), "game"),
    (re.compile(r"^升级广播$", re.I), "room"),
    (re.compile(r"子公会.*退出|退出母公会", re.I), "agency"),
    (re.compile(r"任务列表未完成认证|真人头像认证条款", re.I), "face_auth"),
    (re.compile(r"ChatRoomTab|getWatchHistory|已看过列表", re.I), "room"),
]

# Sheet/模块标题明确非消息域（优先于 IM/私聊 等宽泛 Sheet 规则）
NON_MESSAGE_TITLE_RULES: List[Tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"面板与送礼|礼物与打赏|勋章与展馆|礼物服务|礼物·|背包·|房内礼物|"
            r"互动礼物|幸运礼物|幸运祈愿|国家勋章|礼物消息|礼物面板|"
            r"Redis迁移统计送礼|送礼调用redis|"
            r"游戏数据展示和会话页发钻",
            re.I,
        ),
        "gift",
    ),
    (
        re.compile(
            r"进房·|进房$|麦位·|麦位$|服务端进房|进房欢迎|入场条|"
            r"房间帧|房间等级|房间背景|房间管理员|房间成员",
            re.I,
        ),
        "room",
    ),
    (re.compile(r"账号与注册·语音通话", re.I), "message"),
    (re.compile(r"账号与注册·幸运祈愿", re.I), "gift"),
    (re.compile(r"账号与注册·(?:网络请求|缓存|iOS我的页面)", re.I), "room"),
    (re.compile(r"账号与注册·(?:自定义表情|活动分享)", re.I), "activity"),
    (re.compile(r"账号与注册·(?:分区策略|个人数据)", re.I), "agency"),
    (re.compile(r"账号与注册·(?:拉黑|标签UI)", re.I), "gift"),
    (re.compile(r"账号与注册·谁看过我", re.I), "auth_login"),
    (
        re.compile(
            r"账号与注册·(?:注册|登录|注销|绑定|密码|设置about|资料|区号|欢迎|承接)|"
            r"^注册资料|^登录|注销账号|设置about|账号绑定|账号密码",
            re.I,
        ),
        "auth_login",
    ),
]

MESSAGE_CORE_RE = re.compile(
    r"im|私聊|群聊|聊天|会话|消息|转发|置顶|红点|好友申请|"
    r"消息提醒|钻石到账通知|1v1.*聊天|语音通话|换行|建联|"
    r"关系链|关系改版|关系外显|陌生人聊天|聊天列表",
    re.I,
)

GIFT_TITLE_RE = re.compile(
    r"礼物|送礼|背包|盲盒|勋章|展馆|互动礼物|礼物服务|礼物事件|"
    r"礼物收集|面板与送礼|幸运礼物|返钻|祈愿|定制礼物|礼物面板|"
    r"选中礼物|礼物播放器",
    re.I,
)

# Sheet 名直达（优先于「含房间」宽泛规则与 DEFAULT_FALLBACK）
EARLY_SHEET_RULES: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"^test111$|^App分享$", re.I), "rank"),
    (
        re.compile(
            r"CP活动|cp活动|cp玩法|世界杯|周年庆|万圣节|开斋|大乐透|"
            r"盲盒|宝藏猎人|年末盛典|幸运之王|Recharge offer|"
            r"星座联盟|礼物代言人|谁是大赢家|房主挑战赛|支持球队|"
            r"俄罗斯轮盘|古尔邦|斋月|情人节|活动改版|活动线|"
            r"充值大转盘|充值活动|双向礼物|幸运VISA|星光大使",
            re.I,
        ),
        "activity",
    ),
    (re.compile(r"PK相关活动", re.I), "activity"),
    (re.compile(r"^优化送礼", re.I), "gift"),
    (re.compile(r"^优化薪资", re.I), "agency"),
    (re.compile(r"登陆注册|登录注册|注册登录|短信风控|设备安全|账号安全", re.I), "auth_login"),
    (re.compile(r"客服转工单|语音房客服|帮助中心", re.I), "customer_service"),
    (re.compile(r"^admin|多语言后台|审核后台", re.I), "super_admin"),
    (re.compile(r"ludo|游戏接入|ya party游戏|概率游戏|游戏bridge|游戏开发平台", re.I), "game"),
    (re.compile(r"访客记录|push召回|^push$|PUSH", re.I), "message"),
    (re.compile(r"Checkout支付|稳定币充值|三方支付", re.I), "coin"),
    (re.compile(r"分区策略|个人数据请求|子母公会|公会长", re.I), "agency"),
    (re.compile(r"发布与浏览|moment|动态发布", re.I), "moments"),
    (re.compile(r"主题房活动|活动主题房", re.I), "theme_room"),
]

# Sheet 名优先（避免「送礼」把 IM Sheet 划进礼物）
SHEET_TARGET_RULES: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"主题房|活动主题", re.I), "theme_room"),
    (re.compile(r"^家族|家族改版|创建家族|加入家族|成员管理|家族任务|家族等级|家族基金|家族房间|家族群聊|家族主页|家族广场|家族榜单", re.I), "family"),
    (re.compile(r"im|消息|私聊|群聊|聊天|会话|转发消息|置顶", re.I), "message"),
    (re.compile(r"动态|moment|帖子|视频动态", re.I), "moments"),
    (re.compile(r"币商|充值|提现|转账|钱包|钻石明细", re.I), "coin"),
    (re.compile(r"真人认证|人脸认证|iOS真人认证", re.I), "face_auth"),
    (re.compile(r"^客服·|客服下发|客服快捷|客服评价|券包|快捷回复", re.I), "customer_service"),
    (re.compile(r"超管|工单|审核后台|^审核·", re.I), "super_admin"),
    (re.compile(r"公会|AM|agency|工会长|助理", re.I), "agency"),
    (
        re.compile(
            r"账号与注册|注册资料|登录|注销账号|设置about|账号绑定",
            re.I,
        ),
        "auth_login",
    ),
    (re.compile(r"退出账号|注销账号|设置about|账号绑定|账号密码", re.I), "auth_login"),
    (re.compile(r"^游戏|大冒险|bridge", re.I), "game"),
    (
        re.compile(
            r"摩天轮|活动条|年末盛典|提款机|周年庆|世界杯|开斋|大乐透|"
            r"CP活动|cp活动|cp玩法|盲盒|宝藏猎人|幸运之王|"
            r"Recharge offer|星座联盟|礼物代言人|谁是大赢家|"
            r"房主挑战赛|支持球队|俄罗斯轮盘|活动改版",
            re.I,
        ),
        "activity",
    ),
    (re.compile(r"榜单|排行|打榜|揭榜|荣誉墙|全服榜", re.I), "rank"),
    (re.compile(r"麦位体验卡|20麦", re.I), "room"),
]

# 正文/模块二次规则（优先级高于宽泛词）
BODY_TARGET_RULES: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"主题房", re.I), "theme_room"),
    (re.compile(r"创建家族|加入家族|家族广场|家族基金|族长", re.I), "family"),
    (re.compile(r"语音通话|火山引擎|拨打语音", re.I), "message"),
    (re.compile(r"回复.{0,6}消息|im\s|群聊|私聊|会话页", re.I), "message"),
    (re.compile(r"动态发布|带标签帖子|moment", re.I), "moments"),
    (re.compile(r"币商|充值页|提现|稳定币", re.I), "coin"),
    (re.compile(r"真人认证|人脸", re.I), "face_auth"),
    (re.compile(r"客服后台|快捷回复|客服下发|客服评价|券包", re.I), "customer_service"),
    (re.compile(r"超管|审核后台|设备拉黑|工单", re.I), "super_admin"),
    (re.compile(r"网络速度|网速检测", re.I), "room"),
    (re.compile(r"礼物面板|背包礼物|盲盒|勋章|展馆|幸运礼物", re.I), "gift"),
    (re.compile(r"大冒险|游戏bridge", re.I), "game"),
    (re.compile(r"语音房|进房|麦位|房间背景|房间等级|房间管理员", re.I), "room"),
]

# 同一 Sheet 内合并键
MERGE_MODULE_RULES: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"^回复.+消息", re.I), "IM-回复单条消息（各类型）"),
    (re.compile(r"^【主态】", re.I), "PK-主态相关"),
    (re.compile(r"^【客态】", re.I), "PK-客态相关"),
    (re.compile(r"^主活动页面", re.I), "主活动页面"),
    (re.compile(r"^优化需求", re.I), "优化需求"),
    (re.compile(r"^优化$|^优化-", re.I), "优化需求"),
    (re.compile(r"体验卡", re.I), "20麦位体验卡"),
    (re.compile(r"^语音房-", re.I), "语音房-各模式"),
]


def _norm_module_name(name: str) -> str:
    s = SAME_AS_SUFFIX_RE.sub("", name).strip()
    s = re.sub(r"^\d+[、.．\s]*", "", s)
    return s.strip()


def _sheet_implies_non_gift(sheet: str, module: str = "") -> bool:
    title = _title_blob(sheet, module).lower()
    if any(pat.search(title) for pat, _ in TITLE_DOMAIN_RULES):
        return True
    return bool(
        re.search(
            r"im|消息|私聊|群聊|房间|麦位|pk|跨房|进房|语音房|语音通话|登录|注册|"
            r"币商|动态|moment|主题房|家族|客服|超管|公会|摩天轮|榜单|活动条|"
            r"网络速度|火山引擎|审核后台|域名替换|钻石明细",
            title,
            re.I,
        )
    )


# 房间 PK / 跨房 PK（仅按 Excel Sheet 名判定，避免正文含「PK」误迁入）
ROOM_PK_SHEET_RE = re.compile(
    r"^(PK|pk)(\s|邀请和匹配|邀请|准备|流程|关闭|房间操作|房间|活动|提款机|功能|模式|胜利|首杀|增加)|"
    r"^pk$|"
    r"PK增加|PK胜利|PK首杀|PK模式|"
    r"跨房\s*PK|跨房PK|跨房pk优化|跨房PK优化|跨房PK分区|"
    r"乱斗\s*PK|乱斗PK|"
    r"团战\s*PK|团战PK|"
    r"团队\s*PK|团队PK|"
    r"推荐帧.*PK|PK.*推荐帧|"
    r"PK提款机|PK分区|"
    r"1v1\s*PK|1v1\s*pk",
    re.I,
)


def is_room_pk_domain(sheet: str, module: str, text: str) -> bool:
    """仅当 Excel Sheet 名属于房间/跨房 PK 域时归入 房间PK.md。"""
    sn = (sheet or "").strip()
    mn = (module or "").strip()
    if not sn:
        return False
    if ROOM_PK_SHEET_RE.search(sn):
        return True
    if re.match(r"^pk", sn, re.I):
        return True
    # 精确匹配常见 Sheet 标题
    if sn in {
        "PK邀请和匹配",
        "PK准备",
        "PK流程",
        "PK关闭",
        "PK房间操作",
        "PK活动",
        "PK提款机",
        "乱斗PK",
        "团战PK增加武器",
        "团队PK支持上下麦（陈墨）",
        "跨房PK优化",
        "跨房PK分区策略优化",
        "PK提款机优化（丁亮）",
        "推荐帧增加PK+房间列表背景镜像",
        "PK 模式增加进房特效",
        "PK 胜利展示信息修改",
        "PK 首杀",
        "PK增加贡献榜",
        "pk",
        "pk时间效果优化",
    }:
        return True
    if WEAK_AGGREGATE_SHEET_RE.search(sn) and re.search(
        r"PK|1v1\s*pk|开启PK|pk时间", mn, re.I
    ):
        return True
    if re.search(r"房间PK|房间\s*PK", sn, re.I):
        return True
    return False


def _is_gift_domain(sheet: str, module: str, text: str) -> bool:
    if _sheet_implies_non_gift(sheet, module):
        return False
    title = _title_blob(sheet, module)
    if GIFT_TITLE_RE.search(title):
        return True
    # 仅正文含「送礼」且标题也贴近礼物域时才归入礼物（避免混合 xlsx 误伤）
    if GIFT_TITLE_RE.search(f"{module} {sheet}") and re.search(
        r"礼物|送礼|背包|盲盒|勋章|展馆", text, re.I
    ):
        return True
    return False


_CS_SERVICE_TITLE_RE = re.compile(
    r"^客服·|·客服·|客服下发|客服快捷|客服态|客服评价|客服系统|券包|快捷回复|"
    r"帮助中心|钻石到账通知|钻石补偿",
    re.I,
)
_CS_SUPER_TITLE_RE = re.compile(
    r"^审核·|·审核·|超管|审核后台|设备拉黑|后台新增|后台设备|用户关系迁移|"
    r"权限优化|主播成长激励|商城新增上麦|点击按钮返回顶部",
    re.I,
)


def classify_cs_admin_target(title: str, sheet: str, text: str) -> str:
    """原客服与超管域：按标题/路径拆为 customer_service 或 super_admin。"""
    if _CS_SERVICE_TITLE_RE.search(title):
        return "customer_service"
    if _CS_SUPER_TITLE_RE.search(title):
        return "super_admin"
    parts = (sheet or "").split("·")
    if "客服" in parts and "审核" not in parts and "超管" not in parts:
        return "customer_service"
    if "审核" in parts or "超管" in parts:
        return "super_admin"
    if re.search(r"客服|快捷回复|券包|客服评价", text, re.I):
        if not re.search(r"审核后台|超管|设备拉黑", text, re.I):
            return "customer_service"
    if re.search(r"超管|审核后台|设备拉黑|工单", text, re.I):
        return "super_admin"
    return "super_admin"


def classify_target(b: CaseBlock) -> str:
    sheet = b.sheet or ""
    mod = b.module or ""
    text = f"{sheet} {mod} {b.body} {b.source_file}".lower()
    sn = sheet.lower()
    mn = mod.lower()

    # 房间 PK 优先于「房间」「游戏」
    if is_room_pk_domain(sheet, mod, text):
        return "room_pk"

    title = _title_blob(sheet, mod)

    for pat, target in EARLY_SHEET_RULES:
        if pat.search(sheet):
            return target

    for pat, target in MODULE_DOMAIN_RULES:
        if pat.search(mod) or pat.search(title):
            return target

    # Sheet 路径前缀（须早于 TITLE/DOMAIN 中「主播薪资」等宽泛规则）
    for pat, target in CROSS_DOMAIN_PREFIX_RULES:
        if pat.search(sheet) or pat.search(title):
            return target

    # 精确标题优先（避免 DOMAIN_ROUTING 中「首充」等子串误伤合订 Sheet）
    for pat, target in TITLE_DOMAIN_RULES:
        if pat.search(title):
            return target

    # 非消息域优先（避免「谁看过我」「优化部分」等被语音/关系规则误判进消息）
    for pat, target in NON_MESSAGE_TITLE_RULES:
        if pat.search(title):
            return target

    for pat, target in DOMAIN_ROUTING_RULES:
        if pat.search(title):
            return target

    # Sheet 名优先（高置信）；消息域需标题含消息核心语义，避免「私聊与群聊·礼物*」误入
    for pat, target in SHEET_TARGET_RULES:
        if not pat.search(sheet):
            continue
        if target == "message" and not MESSAGE_CORE_RE.search(title):
            continue
        return target

    # Sheet 名强约束：明显房间域（须在活动/榜单等规则之后，避免「房间内活动」误留房间）
    if re.search(r"^房间|进房·|麦位·|成员与等级·|界面与运营·", sheet, re.I):
        if not re.search(r"礼物", sheet, re.I):
            return "room"
    if re.search(r"房间", sheet, re.I) and not re.search(r"礼物|活动|客服|游戏", sheet, re.I):
        return "room"

    # 模块级强规则
    if re.search(r"^回复.+消息", mn):
        return "message"
    if re.search(r"麦位体验卡|20麦", mn + sn):
        return "room"
    if is_room_pk_domain(sheet, mod, text):
        return "room_pk"

    # 正文关键词
    for pat, target in BODY_TARGET_RULES:
        if pat.search(text):
            # 正文命中礼物，但 Sheet 明显是房间/消息 → 不划进礼物
            if target == "gift" and _sheet_implies_non_gift(sheet, mod):
                continue
            return target

    if _is_gift_domain(sheet, mod, text):
        return "gift"
    if re.search(r"语音房|进房|麦位|房间背景|房间等级|房间管理员|房间成员", text + sn + mn):
        return "room"
    if is_room_pk_domain(sheet, mod, text):
        return "room_pk"
    if re.search(r"大冒险|gamebridge", text + sn + mn):
        return "game"
    if MESSAGE_CORE_RE.search(title):
        return "message"

    # 原「客服与超管」混合域：按标题拆分为客服 / 超管
    if re.search(r"客服与超管|客服|超管|审核·|审核后台", title, re.I):
        return classify_cs_admin_target(title, sheet, text)

    # 正文强域信号（Sheet 名为「优化需求」等泛化标题时）
    for pat, target in DOMAIN_ROUTING_RULES:
        if pat.search(text):
            return target

    # 合订 Sheet：模块名优先于默认落房间
    leaf = _sheet_leaf(sheet)
    if WEAK_AGGREGATE_SHEET_RE.search(sheet) or WEAK_AGGREGATE_SHEET_RE.search(leaf):
        for pat, target in MODULE_DOMAIN_RULES:
            if pat.search(mod):
                return target
        if re.search(r"^VIP|^vip", mod, re.I) or re.search(r"VIP\d|vip\d", mod, re.I):
            return "gift"
        if re.search(r"送礼|礼物动效|盲盒", mod, re.I):
            return "gift"
        if re.search(r"薪资|公会", mod, re.I):
            return "agency"
        if re.search(r"家族", mod, re.I):
            return "family"
        if is_room_pk_domain(sheet, mod, text):
            return "room_pk"

    return DEFAULT_FALLBACK_TARGET


def merge_cluster_key(sheet: str, module: str) -> str:
    base = _norm_module_name(module)
    for pat, key in MERGE_MODULE_RULES:
        if pat.search(base):
            return key
    sl = sheet.lower()
    if "pk" in sl or "跨房" in sheet:
        if any(k in base for k in ("邀请", "匹配")):
            return "PK-邀请与匹配"
        if any(k in base for k in ("准备", "倒计时", "开启")):
            return "PK-准备阶段"
        if "流程" in base or "结束" in base:
            return "PK-流程与结束"
        if any(k in base for k in ("下麦", "上麦", "换麦", "房间操作", "房间功能")):
            return "PK-房间操作"
    if base.startswith("获得主页面") or base.startswith("活动主页面"):
        return "活动主页面相关"
    return base or module


DEFAULT_SHEET_RE = re.compile(r"(?i)sheet\d+")


def is_default_sheet_name(name: str) -> bool:
    return bool(DEFAULT_SHEET_RE.search((name or "").strip()))


def pick_latest_by_key(
    blocks: List[CaseBlock],
) -> Dict[Tuple[str, str, str], CaseBlock]:
    """(target, sheet, module) -> 最新块。"""
    best: Dict[Tuple[str, str, str], CaseBlock] = {}
    for b in blocks:
        sheet = b.sheet or "未归类需求"
        if is_default_sheet_name(sheet):
            continue
        t = classify_target(b)
        key = (t, sheet, b.module)
        if key not in best or b.version_tuple > best[key].version_tuple:
            best[key] = b
    return best


def group_for_output(
    latest: Dict[Tuple[str, str, str], CaseBlock],
) -> Dict[str, Dict[str, Dict[str, List[CaseBlock]]]]:
    """
    target -> sheet -> merge_cluster -> [blocks]
    同 cluster 下多个 module 作为变体保留（已是最新版本集）。
    """
    tree: Dict[str, Dict[str, Dict[str, List[CaseBlock]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for (target, sheet, module), b in latest.items():
        cluster = merge_cluster_key(sheet, module)
        bucket = tree[target][sheet][cluster]
        if not any(x.module == b.module for x in bucket):
            bucket.append(b)
    return tree


def render_cluster_blocks(cluster: str, blocks: List[CaseBlock]) -> str:
    """渲染一个合并后的 ### 章节。"""
    blocks = sorted(blocks, key=lambda x: (x.is_variant, x.module))
    out: List[str] = []

    if len(blocks) == 1 and not blocks[0].parent_module:
        b = blocks[0]
        title = _norm_module_name(b.module) or cluster
        out.append(f"### {title}\n")
        out.append(content_opt.render_block_header(b))
        out.append(content_opt.render_body_kb(b.body))
        out.append("")
        return "\n".join(out)

    out.append(f"### {cluster}\n")
    for b in blocks:
        label = b.module
        if b.parent_module and b.module != b.parent_module:
            label = f"{b.parent_module} / {b.module}"
        out.append(f"\n#### {label}\n")
        out.append(content_opt.render_block_header(b))
        out.append(content_opt.render_body_kb(b.body))
        out.append("")
    return "\n".join(out).strip()


def build_from_tree(
    title: str,
    sheets: Dict[str, Dict[str, List[CaseBlock]]],
) -> str:
    """按 tree[sheet][cluster] 渲染；复用 build_document 的目录逻辑需适配。"""
    # 转成 group_blocks 结构：sheet -> cluster -> blocks
    grouped: Dict[str, Dict[str, List[CaseBlock]]] = {}
    for sheet, clusters in sheets.items():
        grouped[sheet] = {}
        for cluster, blist in clusters.items():
            grouped[sheet][cluster] = blist

    sheet_names = sorted(
        (s for s in grouped.keys() if not is_default_sheet_name(s)),
        key=lambda s: (s == "未归类需求", s),
    )
    toc_lines = ["## 目录", ""]
    for sn in sheet_names:
        toc_lines.append(f"- {sn}")
    toc_lines.append("")

    parts = [
        f"# {title}",
        "",
        "> **文档类型**：产品规则与验收要点知识库（由版本需求整理，非测试执行清单）",
        "",
        "| 项 | 说明 |",
        "|---|---|",
        "| 组织方式 | `## 业务主题` → `### 功能点` → 场景小节与规则列表 |",
        f"| 版本口径 | {content_opt.VERSION_TABLE_BLURB} |",
        "| 索引 | 下方目录为文内业务主题 |",
        "",
        "---",
        "",
        "\n".join(toc_lines),
        "---",
        "",
    ]

    for sn in sheet_names:
        clusters = grouped[sn]
        parts.append(f"## {sn}")
        parts.append("")
        for cluster in sorted(clusters.keys(), key=lambda x: (not x or not x[0].isdigit(), x)):
            sec = render_cluster_blocks(cluster, clusters[cluster])
            if sec:
                parts.append(sec)
                parts.append("")

    text = "\n".join(parts)
    return re.sub(r"\n{4,}", "\n\n\n", text).strip() + "\n"


def load_all_blocks(root: Path) -> List[CaseBlock]:
    blocks: List[CaseBlock] = []
    for p in sorted(root.glob("*.md")):
        if p.name.lower() == "readme.md":
            continue
        blocks.extend(extract_blocks(p.read_text(encoding="utf-8")))
    return blocks


def main() -> None:
    ap = argparse.ArgumentParser(description="知识库按内容拆分/合并")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root: Path = args.root
    all_blocks = load_all_blocks(root)
    if not all_blocks:
        raise SystemExit("未解析到任何用例块")

    latest = pick_latest_by_key(all_blocks)
    tree = group_for_output(latest)

    stats: Dict[str, int] = defaultdict(int)
    for target, sheets in tree.items():
        for sheet, clusters in sheets.items():
            stats[target] += len(clusters)

    for target, count in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {KB_FILE_NAMES.get(target, target)}: {count} 个合并后模块")

    if args.dry_run:
        print(f"dry-run: {len(all_blocks)} blocks -> {len(latest)} latest keys")
        return

    for target, fname in KB_FILE_NAMES.items():
        sheets_map = tree.get(target, {})
        title = fname.replace(".md", "")
        if not sheets_map:
            md = (
                f"# {title}\n\n"
                "- **说明**：当前无归类用例块（可能已全部迁入其他大模块）。\n"
            )
        else:
            md = build_from_tree(title, sheets_map)
        if target == "room_pk" and sheets_map:
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
                "> **范围**：房间内 PK、跨房 PK、乱斗/团战/团队 PK；"
                "PK 邀请～关闭全流程、PK 房间操作、PK 提款机等。\n"
                "> **阅读**：按 **Excel Sheet** 查目录；冲突以最新版本为准。\n\n"
                "---\n\n"
                f"{pk_map}"
            )
            if md.startswith(f"# {title}"):
                # 去掉 build_from_tree 重复说明段，保留目录起正文
                rest = md.split("\n---\n\n", 1)
                body = rest[-1] if len(rest) > 1 else md
                if body.lstrip().startswith(f"# {title}"):
                    body = body.split("\n", 1)[1]
                md = intro + body.lstrip("\n")
        (root / fname).write_text(md, encoding="utf-8")

    # 格式收尾
    opt_path = Path(__file__).parent / "optimize_kb_docs.py"
    if opt_path.exists():
        import subprocess

        subprocess.run(
            [sys.executable, str(opt_path), "--root", str(root)],
            check=False,
        )

    print(f"split-merge done -> {root}")


if __name__ == "__main__":
    main()
