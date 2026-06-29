"""MOA CLI 入口。"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .client import (
    MoaClient,
    extract_ec_em_result,
    extract_inner_result,
    outer_success,
    parse_current_exp_from_inner,
)
from .config import level_by_exp, room_level_thresholds
from .diamond import parse_diamond_account_summary
from .family import (
    parse_family_exp_summary,
    parse_family_fund_summary,
    parse_family_fund_tier_set_count,
    parse_family_members_summary,
    parse_user_joined_family_summary,
)
from .env import load_local_env, load_online_env
from .online_config import online_defaults, online_query_login_status
from .flows import (
    build_family_level_upgrade_payload,
    build_room_level_upgrade_payload,
    build_vip_level_upgrade_payload,
    needs_family_fund_reward_setup,
    needs_family_level_upgrade,
    needs_room_level_upgrade,
    needs_vip_level_upgrade,
    run_family_fund_reward_setup,
    run_id_auth_fix_failure,
)
from .family_detail import needs_family_detail, needs_family_detail_by_user, run_family_detail
from .package_gift import run_package_gift_send
from .time_utils import resolve_family_fund_week_key
from .user_area import USER_AREA_CODES
from .user_login import normalize_mobile_login, parse_login_status_summary, resolve_phone_area_code
from .user_prop import parse_user_prop_summary
from .vip import parse_vip_info_summary
from .wealth_charm import parse_charm_info_summary, parse_wealth_info_summary
from .payload import load_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="在本地复现 MOA httpproxy execute 调用")
    parser.add_argument("--entry-url", default=os.environ.get("MOA_ENTRY_URL"), help="httpproxy 入口完整 URL")
    parser.add_argument("--cookie", default=os.environ.get("MOA_COOKIE"), help="Cookie")
    parser.add_argument("--timeout-ms", type=int, default=5000, help="HTTP 超时（毫秒），默认 5000")
    parser.add_argument(
        "--线上环境",
        dest="online_env",
        action="store_true",
        help="使用线上 MOA（overseas + .env.online.local）；仅当用户提示词含「线上环境」时由 Agent 调用；当前仅支持 --query-user-by-phone",
    )
    parser.add_argument("--host", help='覆盖 payload.settings.host')
    parser.add_argument("--moa-time", type=int, help='覆盖 payload.settings.time（毫秒）')
    parser.add_argument("--group", help='覆盖 payload.settings.group')
    parser.add_argument("--header-type", help='覆盖 payload.settings.headerType')
    parser.add_argument("--service-url", help='覆盖 payload.url')
    parser.add_argument("--moa-method", help='覆盖 payload.method')
    parser.add_argument("--region", help='覆盖 payload.region')
    parser.add_argument("--env", help='覆盖 payload.env')
    parser.add_argument("--cluster", help='覆盖 payload.cluster')
    parser.add_argument("--server", help='覆盖 payload.server')
    parser.add_argument("--momo-id", help="覆盖 payload.momoId")
    parser.add_argument("--momo-name", help="覆盖 payload.momoName")
    parser.add_argument("--header", help="覆盖 payload.header")
    parser.add_argument("--dump-payload", action="store_true", help="输出最终 payload 到 stderr")
    parser.add_argument("--origin", default=os.environ.get("MOA_ORIGIN"))
    parser.add_argument("--referer", default=os.environ.get("MOA_REFERER"))
    parser.add_argument("--user-agent", default=os.environ.get("MOA_USER_AGENT"))
    parser.add_argument("--request-source", default=os.environ.get("MOA_REQUEST_SOURCE"))

    src = parser.add_mutually_exclusive_group(required=False)
    src.add_argument("--payload-file", help="包含完整 payload 的 JSON 文件路径")
    src.add_argument("--payload", help="完整 payload JSON 字符串")

    parser.add_argument("--expr", help="覆盖 params[0].value / txt 的表达式")
    parser.add_argument("--room-id", help="房间 ID")
    parser.add_argument("--exp", type=int, help="增加的经验值")
    parser.add_argument("--level", type=int, help="目标房间等级")
    parser.add_argument("--current-exp", type=int, help="当前房间经验值")
    parser.add_argument("--query-current", action="store_true", help="查询当前房间经验值与等级")

    parser.add_argument("--vip-user-id", help="VIP 用户 ID")
    parser.add_argument("--vip-exp", type=int, help="增加的 VIP 经验值")
    parser.add_argument("--vip-level", type=int, help="目标 VIP 等级")
    parser.add_argument("--vip-current-exp", type=int, help="当前 VIP 经验值")
    parser.add_argument("--vip-query-current", action="store_true", help="查询当前 VIP 经验值与等级（getVipInfo）")
    parser.add_argument("--vip-del-user-id", help="清除 VIP 信息")
    parser.add_argument("--vip-try-user-id", help="VIP 体验卡：用户 ID（dispatchTryVip）")
    parser.add_argument("--vip-try-level", type=int, help="VIP 体验卡：体验等级 1-10")
    parser.add_argument(
        "--vip-try-duration-seconds",
        type=int,
        help="VIP 体验卡：体验时长（秒）；1 天=86400",
    )
    parser.add_argument(
        "--custom-gift-reset-user-id",
        help="定制礼物：重置上传次数 userId（resetExpireTime）",
    )
    parser.add_argument("--custom-gift-rank-gift-id", help="定制礼物榜单：礼物 ID")
    parser.add_argument(
        "--custom-gift-rank-delete",
        action="store_true",
        help="清除定制礼物榜单数据（delCustomGiftRankData；需配合 --custom-gift-rank-gift-id）",
    )
    parser.add_argument("--custom-gift-rank-active-value", type=int, help="定制礼物榜单：增加活跃值（mockCustomGiftRankData）")
    parser.add_argument(
        "--custom-gift-rank-period",
        choices=["NOW", "PRE", "PRE_PRE"],
        help="定制礼物榜单周期：NOW=本周 PRE=上周 PRE_PRE=上上周（默认 PRE）",
    )
    parser.add_argument(
        "--custom-gift-rank-area",
        choices=sorted(USER_AREA_CODES),
        help="定制礼物榜单大区（默认 MENA）",
    )
    parser.add_argument(
        "--custom-gift-rank-user-id",
        help="定制礼物榜单 header 中的 userId（默认 config.json custom_gift_rank.defaultUserId）",
    )

    parser.add_argument("--noble-user-id", help="贵族月消费值：用户 ID（incrNobelLevel）")
    parser.add_argument("--noble-exp", type=int, help="贵族月消费值：增加量")
    parser.add_argument("--noble-level", type=int, help="贵族等级：目标 lv1-lv6")
    parser.add_argument("--noble-current-exp", type=int, help="贵族月消费值：当前值（配合 --noble-level，默认 0）")

    parser.add_argument("--family-id", help="家族声望值：家族 ID（addFamilyActiveValueBySystem）")
    parser.add_argument("--family-exp", type=int, help="家族声望值：增加量")
    parser.add_argument("--family-decrease-exp", type=int, help="家族声望值：衰减量（decreaseFamilyActiveValue，传正值）")
    parser.add_argument("--family-level", type=int, help="家族等级：目标 lv1-lv10")
    parser.add_argument("--family-current-exp", type=int, help="家族声望值：当前值（配合 --family-level，默认 0）")
    parser.add_argument("--family-query-current", action="store_true", help="查询当前家族声望值与等级（增量 0）")
    parser.add_argument("--family-query-members", action="store_true", help="查询家族全部成员 userId（getFamilyMembers）")
    parser.add_argument(
        "--family-query-joined-user-id",
        help="按 userId 查询所属家族 ID（getUserJoinedFamily）",
    )
    parser.add_argument(
        "--family-leave-user-id",
        help="移除家族成员（leave；params={userId} json）",
    )
    parser.add_argument(
        "--family-detail",
        action="store_true",
        help="查询家族详情：Admin 家族信息 + MOA 成员 userId（需 --family-id）",
    )
    parser.add_argument(
        "--family-detail-by-user-id",
        help="按 userId 查家族详情：MOA 查家族 id → Admin 家族信息 + MOA 成员列表",
    )
    parser.add_argument("--family-fund-tier", choices=["A", "B", "C"], help="家族基金档位（FamilyFundService.batchSetFamilyFundTierForTest）")
    parser.add_argument("--family-fund-tier-flag", type=int, default=0, help="设置基金档位 flag（默认 0；result=0 表示未更新）")
    parser.add_argument("--family-fund-ids", help="家族基金档位：家族 ID 列表，逗号分隔（默认用 --family-id）")
    parser.add_argument("--family-fund-reward-diamonds", type=int, help="一键设置家族基金返奖钻石（自动匹配档位+贡献值）")
    parser.add_argument("--family-fund-contrib", type=int, help="家族基金贡献值：增量（incrFundFamilyTotal；0=查询）")
    parser.add_argument(
        "--family-fund-week",
        help="家族基金周期（该周周一 YYYYMMDD 或任意日期，默认本周；也可 YYYYMMDD-week）",
    )
    parser.add_argument("--family-fund-clear", action="store_true", help="清除家族基金贡献值（delFamilyFundRankTest）")
    parser.add_argument(
        "--family-fund-week-offset",
        type=int,
        default=0,
        help="清除基金贡献值时的周偏移：0=本周（默认），-1=上周",
    )
    parser.add_argument("--family-member-fund-user-id", help="成员家族基金贡献值：用户 ID（batchIncrFundContribution）")
    parser.add_argument(
        "--family-member-fund-contrib",
        type=int,
        help="成员家族基金贡献值：增加量（API 自动 ×2 传参）",
    )

    parser.add_argument("--id-auth-user-id", help="查询实名认证记录")
    parser.add_argument(
        "--id-auth-output",
        choices=["latest-reason", "json"],
        default="latest-reason",
        help="实名认证查询输出格式",
    )
    parser.add_argument("--id-auth-reset-expire-user-id", help="设置认证过期时间 userId")
    parser.add_argument("--id-auth-expire-ms", type=int, help="认证过期毫秒时间戳")
    parser.add_argument(
        "--id-auth-expire-at",
        help="认证过期时间（自然语言/日期），如 tomorrow/明天、+1d、2026-05-30 23:59:59",
    )
    parser.add_argument("--id-auth-delete-user-id", help="清除用户认证信息")
    parser.add_argument("--id-auth-del-relation-user-id", help="按场景删除真人认证 userId")
    parser.add_argument(
        "--id-auth-relation-scene",
        choices=["DEALER", "ANCHOR"],
        help="真人认证场景：DEALER=币商，ANCHOR=普通/主播",
    )
    parser.add_argument("--id-auth-fix-failure-user-id", help="解决认证失败（清 reason 关联账号）")

    parser.add_argument("--user-prop-query-user-id", help="查询用户拥有装扮 userId（queryOwnPropList）")
    parser.add_argument("--user-prop-type-code", help="装扮 propTypeCode，如 10144=资料页背景")
    parser.add_argument("--user-prop-lang", default="en", help="queryOwnPropList lang（默认 en）")
    parser.add_argument("--user-prop-app-id", type=int, help="queryOwnPropList appId（默认 2005）")
    parser.add_argument(
        "--user-prop-output",
        choices=["summary", "json"],
        default="summary",
        help="装扮查询输出格式：summary=摘要（默认）；json=完整响应 JSON",
    )

    parser.add_argument("--diamond-user-id", help="发放钻石 userId")
    parser.add_argument("--diamond-num", type=int, help="发放钻石数量")
    parser.add_argument("--diamond-query-user-id", help="查询用户钻石余额 userId（queryUserAccount）")
    parser.add_argument(
        "--change-user-area-user-id",
        help="修改用户大区 userId（changeAreaForTest；params=userId, 大区代码）",
    )
    parser.add_argument(
        "--user-area",
        choices=sorted(USER_AREA_CODES),
        default="MENA",
        help="目标大区代码：MENA/TR/RU/SEA/SA/CN（默认 MENA）",
    )
    parser.add_argument(
        "--query-user-by-phone",
        help="按手机号查询 userId（queryLoginStatusV2；data 为空表示未注册）",
    )
    parser.add_argument(
        "--cancel-user",
        dest="cancel_user_id",
        metavar="USER_ID",
        help="注销账号 userId（voga-mts-user-backdoor；userCancelService.cancelUserReal）",
    )
    parser.add_argument(
        "--charm-query-user-id",
        help="查询魅力等级 userId（getCharmInfoNoAvatar）",
    )
    parser.add_argument(
        "--wealth-query-user-id",
        help="查询财富等级 userId（getWealthInfoNoAvatar）",
    )
    parser.add_argument(
        "--wealth-charm-output",
        choices=["summary", "json"],
        default="summary",
        help="财富/魅力查询输出格式：summary=摘要（默认）；json=完整响应 JSON",
    )
    parser.add_argument(
        "--phone-area-code",
        default=None,
        help="手机号区号（测试默认 86；--线上环境 默认 966；也可在号码中带 +区号）",
    )
    parser.add_argument("--phone-app-id", type=int, help="queryLoginStatusV2 的 appId（默认 config.json 中 2005）")
    parser.add_argument(
        "--phone-output",
        choices=["summary", "json"],
        default="summary",
        help="手机号查 userId 输出格式：summary=摘要（默认）；json=完整响应 JSON",
    )
    parser.add_argument(
        "--diamond-output",
        choices=["summary", "json"],
        default="summary",
        help="钻石查询输出格式：summary=摘要（默认）；json=完整响应 JSON",
    )
    parser.add_argument("--package-gift-user-id", help="背包礼物 userId（下发）或送礼方（--package-gift-send）")
    parser.add_argument("--package-gift-num", type=int, help="每种礼物 productNum（默认 1）")
    parser.add_argument("--package-gift-give-user-id", help="giveUserId（addPackageGift 可选）")
    parser.add_argument(
        "--package-gift-send",
        action="store_true",
        help="背包礼物流程：默认 addPackageGift + sendMiddlePackageGift，但 success 以真实到账为准（见 --package-gift-add-only）",
    )
    parser.add_argument(
        "--package-gift-add-only",
        action="store_true",
        help="仅 addPackageGift 下发到送礼方背包（MOA 可稳定完成的部分）",
    )
    parser.add_argument(
        "--package-gift-accept-moa-send",
        action="store_true",
        help="信任 sendMiddlePackageGift 的 result=true（不推荐；通常未触发 v2/gift/send）",
    )
    parser.add_argument("--package-gift-to-user-id", help="背包送礼收礼方 userId")
    parser.add_argument(
        "--package-gift-base-id",
        help="背包礼物 baseProductId（默认 config package_gift.sendDefaultBaseProductId=2005001494 Chocolate 99钻）",
    )
    parser.add_argument(
        "--package-gift-skip-add",
        action="store_true",
        help="背包送礼时跳过 addPackageGift（送礼方背包已有该礼物时使用）",
    )

    parser.add_argument(
        "--room-set-level-room-id",
        help="设置房间等级：房间 ID（downgradeRoomLevelForTest）",
    )
    parser.add_argument("--room-set-level", type=int, help="设置房间等级：目标等级（downgradeRoomLevelForTest）")

    parser.add_argument("--room-bot-room-id", help="增加房间机器人：房间 ID（addOnlineUsersToRoom）")
    parser.add_argument("--room-bot-total", type=int, help="增加房间机器人：在线机器人总数")
    parser.add_argument("--room-bot-on-mic", type=int, help="增加房间机器人：麦上机器人数量")

    parser.add_argument("--pk-rank-user-id", help="PK榜-增加PK值：用户 ID（handlePkRank）")
    parser.add_argument("--pk-rank-value", type=int, help="PK榜-增加PK值：增加的 PK 值")
    parser.add_argument("--user-reg-time-user-id", help="用户-查询注册时间：用户 ID（userVipTaskDao.getUserRegTime）")
    parser.add_argument("--user-set-reg-time-user-id", help="用户-设置注册时间：用户 ID（userVipTaskDao.saveUserRegTime）")
    parser.add_argument(
        "--user-set-reg-time-at",
        help="用户-设置注册时间：目标时间（毫秒时间戳 或 YYYY-MM-DD HH:MM:SS 或 yesterday/2天前 等）",
    )
    parser.add_argument("--user-home-country-user-id", help="用户-修改注册国家：用户 ID（mdp-user-service updateUser）")
    parser.add_argument("--user-home-country", help="用户-修改注册国家：国家代码（如 EG、SA、TR）")
    parser.add_argument("--find-ip", help="IP-查询归属地：IP 地址（pip-new-search-service findIp）")
    parser.add_argument(
        "--pk-rank-query-week",
        help="PK榜-查询数值：周榜周期（周一 YYYYMMDD 或 this/本周；默认本周）",
    )
    parser.add_argument(
        "--pk-rank-settle-week-offset",
        type=int,
        help="PK榜-周结算发奖：周偏移（0=本周，-1=上周；calculateAndDistributeWeekPrize）",
    )

    parser.add_argument(
        "--room-day-rank-area",
        choices=["MENA", "TR", "RU", "SEA", "SA", "CN"],
        help="房间日榜奖励下发：大区（dispatchTotalRoomDayRankListPrize；默认 MENA）",
    )
    parser.add_argument(
        "--charm-day-rank-area",
        choices=["MENA", "TR", "RU", "SEA", "SA", "CN"],
        help="魅力日榜奖励下发：大区（dispatchTotalCharmRankListPrizeV2；默认 MENA）",
    )
    parser.add_argument(
        "--contrib-day-rank-area",
        choices=["MENA", "TR", "RU", "SEA", "SA", "CN"],
        help="贡献日榜奖励下发：大区（dispatchTotalContributionRankListPrizeV2；默认 MENA）",
    )
    parser.add_argument(
        "--user-rank-area",
        choices=["MENA", "TR", "RU", "SEA", "SA", "CN"],
        help="用户榜单奖励下发：大区（dispatchTotalUserRankListPrize；默认 MENA）",
    )
    parser.add_argument(
        "--user-rank-time-type",
        choices=["WEEK", "DAY", "MONTH"],
        default="WEEK",
        help="用户榜单奖励下发：周期类型（WEEK=周榜，DAY=日榜，MONTH=月榜；默认 WEEK；MONTH 自动使用 V2 方法）",
    )
    parser.add_argument(
        "--user-rank-cycle",
        choices=["NOW", "PRE"],
        default="NOW",
        help="用户榜单奖励下发：榜单周期（NOW=当前，PRE=上期；默认 NOW）",
    )

    parser.add_argument("--member-lv-room-id", help="房间成员陪伴值：房间 ID（doorIncrMemberLv）")
    parser.add_argument("--member-lv-user-id", help="房间成员陪伴值：用户 ID")
    parser.add_argument("--member-lv-exp", type=int, help="房间成员陪伴值：增加量")
    parser.add_argument("--member-lv-level", type=int, help="房间成员陪伴值：目标成员等级 lv1-lv20")
    parser.add_argument("--member-lv-current-exp", type=int, help="房间成员陪伴值：当前陪伴值（配合 --member-lv-level，默认 0）")
    parser.add_argument(
        "--level-exp-mode",
        choices=["min", "max"],
        default="min",
        help="按等级升级时的目标经验：min=该等级最低阈值（默认）；max=该等级最高经验（下一级阈值-1）",
    )

    parser.add_argument(
        "--cp-ferris-tier",
        type=int,
        choices=[1, 2, 3, 4, 5],
        help="CP摩天轮档位（batchSetCpFerrisWheelTierLevel；1=D、2=C、3=B、4=A、5=S）",
    )
    parser.add_argument(
        "--cp-pairs",
        help="CP 对列表，逗号分隔，格式小uid-大uid（配合 --cp-ferris-tier）",
    )
    parser.add_argument("--cp-pair-left", help="单对 CP 左位 userId（小 uid，配合 --cp-pair-right）")
    parser.add_argument("--cp-pair-right", help="单对 CP 右位 userId（大 uid，配合 --cp-pair-left）")
    parser.add_argument(
        "--cp-ferris-area",
        choices=sorted(USER_AREA_CODES),
        help="CP摩天轮大区（distributeCpFerrisWheelBonusDiamonds / calculateAndDistributeCpFerrisWheelWeekPrize；仅 params[0]）",
    )

    parser.add_argument("--activity-gift-from-user-id", help="活动模拟送礼：送礼方 userId")
    parser.add_argument("--activity-gift-to-user-id", help="活动模拟送礼：收礼方 userId")
    parser.add_argument(
        "--activity-gift-method",
        help="活动模拟送礼：MOA 方法名（如 handleGiftRamadan2026）；也可用 --moa-method",
    )
    parser.add_argument("--activity-gift-flag", help="活动模拟送礼：params[0]，默认 test")
    parser.add_argument("--activity-gift-product-id", help="活动模拟送礼：product_id")
    parser.add_argument("--activity-gift-product-num", type=int, help="活动模拟送礼：product_num")
    parser.add_argument("--activity-gift-price", type=int, help="活动模拟送礼：price")
    parser.add_argument("--activity-gift-real-fee", type=int, help="活动模拟送礼：real_fee")
    parser.add_argument("--activity-gift-total-fee", type=int, help="活动模拟送礼：total_fee")
    parser.add_argument("--activity-gift-room-id", default="", help="活动模拟送礼：room_id（房内送礼时填写）")

    return parser


def _apply_optional_headers(args: argparse.Namespace) -> None:
    for attr, env_key in (
        ("origin", "MOA_ORIGIN"),
        ("referer", "MOA_REFERER"),
        ("user_agent", "MOA_USER_AGENT"),
        ("request_source", "MOA_REQUEST_SOURCE"),
    ):
        value = getattr(args, attr, None)
        if value:
            os.environ[env_key] = value


def _apply_online_moa_args(args: argparse.Namespace, base_dir: str) -> None:
    """线上 MOA：overseas 集群 + .env.online.local；当前仅开放手机号查 userId。"""
    if args.query_user_by_phone is None:
        raise ValueError("线上环境 MOA 当前仅支持 --query-user-by-phone（须用户提示词含「线上环境」）")

    load_online_env(base_dir)
    defaults = online_defaults()

    args.entry_url = os.environ.get("MOA_ONLINE_ENTRY_URL") or defaults.get("entryUrl") or args.entry_url
    args.cookie = os.environ.get("MOA_ONLINE_COOKIE") or args.cookie

    origin = os.environ.get("MOA_ONLINE_ORIGIN") or defaults.get("origin") or ""
    referer = os.environ.get("MOA_ONLINE_REFERER") or defaults.get("referer") or ""
    user_agent = os.environ.get("MOA_ONLINE_USER_AGENT") or ""
    request_source = os.environ.get("MOA_ONLINE_REQUEST_SOURCE") or defaults.get("requestSource") or ""

    if origin:
        os.environ["MOA_ORIGIN"] = origin
        args.origin = origin
    if referer:
        os.environ["MOA_REFERER"] = referer
        args.referer = referer
    if user_agent:
        os.environ["MOA_USER_AGENT"] = user_agent
        args.user_agent = user_agent
    if request_source:
        os.environ["MOA_REQUEST_SOURCE"] = request_source
        args.request_source = request_source

    for field, cfg_key in (("region", "region"), ("env", "env"), ("cluster", "cluster"), ("server", "server")):
        if getattr(args, field, None) is None:
            value = defaults.get(cfg_key)
            if value is not None:
                setattr(args, field, value)

    if args.momo_id is None and defaults.get("momoId"):
        args.momo_id = defaults.get("momoId")
    if args.momo_name is None and defaults.get("momoName"):
        args.momo_name = defaults.get("momoName")

    if not args.payload_file and not args.payload:
        login_cfg = online_query_login_status()
        template_file = str(login_cfg.get("templateFile") or "").strip()
        if template_file:
            repo = os.path.dirname(base_dir)
            args.payload_file = os.path.join(repo, "online", template_file)


def _print_request_info(args: argparse.Namespace, payload: dict[str, object]) -> None:
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    params0: object = None
    params = payload.get("params")
    if isinstance(params, list) and params and isinstance(params[0], dict):
        params0 = params[0].get("value")
    extra = ""
    if isinstance(params0, dict) and "outOrderId" in params0:
        extra = f', outOrderId="{params0.get("outOrderId")}"'
    print(
        "请求信息: "
        f'entry_url="{args.entry_url}", '
        f'service_url="{payload.get("url")}", '
        f'method="{payload.get("method")}", '
        f'host="{settings.get("host", "")}", '
        f'time="{settings.get("time", "")}", '
        f'expr="{params0 if isinstance(params0, str) else ""}"'
        f"{extra}",
        file=sys.stderr,
    )


def _print_level_summary(args: argparse.Namespace, resp: dict[str, object]) -> None:
    if args.query_current:
        inner_ec, inner_em, inner_result = extract_inner_result(resp)
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            raise SystemExit(4)
        current_exp = parse_current_exp_from_inner(inner_result)
        thresholds = room_level_thresholds()
        lv = level_by_exp(current_exp, thresholds)
        next_lv = lv + 1 if (lv + 1) in thresholds else None
        next_threshold = thresholds.get(next_lv) if next_lv else None
        remaining = (next_threshold - current_exp) if next_threshold is not None else None
        print(
            json.dumps(
                {
                    "roomId": args.room_id,
                    "currentExp": current_exp,
                    "level": lv,
                    "nextLevelThreshold": next_threshold,
                    "remainingToNextLevel": remaining,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


def _print_response(args: argparse.Namespace, resp: dict[str, object]) -> None:
    if args.query_user_by_phone is not None and args.phone_output == "summary":
        inner_ec, inner_em, inner_result = extract_inner_result(resp)
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            raise SystemExit(4)
        area_code, mobile = normalize_mobile_login(args.query_user_by_phone, resolve_phone_area_code(args))
        summary = parse_login_status_summary(area_code, mobile, inner_result)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.vip_query_current:
        inner_ec, inner_em, inner_result = extract_inner_result(resp)
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            raise SystemExit(4)
        summary = parse_vip_info_summary(args.vip_user_id, inner_result)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.id_auth_user_id is not None and args.id_auth_output == "latest-reason":
        _print_id_auth_latest_reason(resp)
        return

    if args.user_prop_query_user_id is not None and args.user_prop_output == "summary":
        inner_ec, inner_em, inner_result = extract_inner_result(resp)
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            raise SystemExit(4)
        summary = parse_user_prop_summary(
            args.user_prop_query_user_id,
            args.user_prop_type_code or "",
            inner_result,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.diamond_query_user_id is not None and args.diamond_output == "summary":
        inner_ec, inner_em, inner_result = extract_inner_result(resp)
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            raise SystemExit(4)
        summary = parse_diamond_account_summary(args.diamond_query_user_id, inner_result)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.charm_query_user_id is not None and args.wealth_charm_output == "summary":
        inner_ec, inner_em, inner_result = extract_inner_result(resp)
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            raise SystemExit(4)
        summary = parse_charm_info_summary(args.charm_query_user_id, inner_result)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.wealth_query_user_id is not None and args.wealth_charm_output == "summary":
        inner_ec, inner_em, inner_result = extract_inner_result(resp)
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            raise SystemExit(4)
        summary = parse_wealth_info_summary(args.wealth_query_user_id, inner_result)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.family_query_joined_user_id is not None:
        inner_ec, inner_em, inner_result = extract_inner_result(resp)
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            raise SystemExit(4)
        summary = parse_user_joined_family_summary(args.family_query_joined_user_id, inner_result)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.family_query_members:
        inner_ec, inner_em, inner_result = extract_inner_result(resp)
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            raise SystemExit(4)
        summary = parse_family_members_summary(args.family_id, inner_result)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.family_query_current:
        inner_ec, inner_em, inner_result = extract_inner_result(resp)
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            raise SystemExit(4)
        summary = parse_family_exp_summary(args.family_id, inner_result)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.family_decrease_exp is not None and args.family_id is not None:
        inner_ec, inner_em, inner_result = extract_inner_result(resp)
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            raise SystemExit(4)
        try:
            summary = parse_family_exp_summary(args.family_id, inner_result)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        except RuntimeError:
            print(json.dumps(resp, ensure_ascii=False, indent=2))
        return

    if args.family_fund_tier is not None:
        inner_ec, inner_em, inner_result = extract_inner_result(resp)
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            raise SystemExit(4)
        updated = parse_family_fund_tier_set_count(inner_result)
        if updated <= 0:
            print(f"家族基金档位设置失败：未更新任何家族（updated={updated}）", file=sys.stderr)
            raise SystemExit(4)
        print(
            json.dumps(
                {
                    "updatedFamilyCount": updated,
                    "fundTier": args.family_fund_tier,
                    "familyIds": args.family_fund_ids or args.family_id,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if args.family_fund_contrib == 0 and args.family_id is not None:
        inner_ec, inner_em, inner_result = extract_inner_result(resp)
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            raise SystemExit(4)
        week_key = resolve_family_fund_week_key(args.family_fund_week)
        summary = parse_family_fund_summary(args.family_id, week_key, inner_result)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    print(json.dumps(resp, ensure_ascii=False, indent=2))


def _print_id_auth_latest_reason(resp: dict[str, object]) -> None:
    inner_ec, inner_em, inner_result = extract_inner_result(resp)
    if inner_ec != 0:
        print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
        raise SystemExit(4)
    if not isinstance(inner_result, dict):
        print("无法解析实名认证业务返回 result（不是 object）", file=sys.stderr)
        raise SystemExit(4)
    latest = (inner_result.get("data") or {}).get("list") if isinstance(inner_result.get("data"), dict) else None
    if not isinstance(latest, list) or not latest:
        print("")
    else:
        reason = latest[0].get("reason")
        if isinstance(reason, (dict, list)):
            print(json.dumps(reason, ensure_ascii=False))
        else:
            print("" if reason is None else str(reason))


def main() -> int:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_local_env(base_dir)

    args = build_parser().parse_args()

    try:
        if getattr(args, "online_env", False):
            _apply_online_moa_args(args, base_dir)
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        return 2

    if not args.entry_url:
        print("缺少入口 URL：请传 --entry-url 或设置环境变量 MOA_ENTRY_URL", file=sys.stderr)
        return 2
    if not args.cookie:
        print("缺少 Cookie：请传 --cookie 或设置环境变量 MOA_COOKIE", file=sys.stderr)
        return 2

    _apply_optional_headers(args)
    client = MoaClient(args.entry_url, args.cookie, args.timeout_ms)

    try:
        if args.package_gift_send:
            return run_package_gift_send(args, client)

        if args.id_auth_fix_failure_user_id is not None and args.expr is None:
            return run_id_auth_fix_failure(args, client)

        if needs_family_fund_reward_setup(args):
            return run_family_fund_reward_setup(args, client)

        if needs_family_detail(args) or needs_family_detail_by_user(args):
            return run_family_detail(args, client)

        if needs_vip_level_upgrade(args):
            payload = build_vip_level_upgrade_payload(args, client)
        elif needs_family_level_upgrade(args):
            payload = build_family_level_upgrade_payload(args, client)
        elif needs_room_level_upgrade(args):
            payload = build_room_level_upgrade_payload(args, client)
        else:
            payload = load_payload(args)

        _print_request_info(args, payload)
        if args.dump_payload:
            print("最终 payload（不含 cookie）:", file=sys.stderr)
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)

        resp = client.post(payload)
    except (ValueError, RuntimeError, OSError) as e:
        print(f"执行失败: {e}", file=sys.stderr)
        return 1

    _print_response(args, resp)

    ec, em, _ = extract_ec_em_result(resp)
    if not outer_success(ec):
        print(f"MOA 返回失败: ec={ec}, em={em or 'ec!=0'}", file=sys.stderr)
        return 3

    try:
        _print_level_summary(args, resp)
    except SystemExit as e:
        return int(e.code)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
