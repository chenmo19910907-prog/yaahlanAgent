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
from .family import parse_family_exp_summary, parse_family_fund_summary, parse_family_fund_tier_set_count
from .env import load_local_env
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
from .time_utils import resolve_family_fund_week_key
from .user_login import normalize_mobile_login, parse_login_status_summary
from .vip import parse_vip_info_summary
from .payload import load_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="在本地复现 MOA httpproxy execute 调用")
    parser.add_argument("--entry-url", default=os.environ.get("MOA_ENTRY_URL"), help="httpproxy 入口完整 URL")
    parser.add_argument("--cookie", default=os.environ.get("MOA_COOKIE"), help="Cookie")
    parser.add_argument("--timeout-ms", type=int, default=5000, help="HTTP 超时（毫秒），默认 5000")
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
    parser.add_argument("--id-auth-fix-failure-user-id", help="解决认证失败（清 reason 关联账号）")

    parser.add_argument("--diamond-user-id", help="发放钻石 userId")
    parser.add_argument("--diamond-num", type=int, help="发放钻石数量")
    parser.add_argument("--diamond-query-user-id", help="查询用户钻石余额 userId（queryUserAccount）")
    parser.add_argument(
        "--query-user-by-phone",
        help="按手机号查询 userId（queryLoginStatusV2；data 为空表示未注册）",
    )
    parser.add_argument("--phone-area-code", default="86", help="手机号区号（默认 86；也可在号码中带 +86）")
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
    parser.add_argument("--package-gift-user-id", help="下发背包礼物 userId")
    parser.add_argument("--package-gift-num", type=int, help="每种礼物 productNum")
    parser.add_argument("--package-gift-give-user-id", help="giveUserId")

    parser.add_argument("--room-bot-room-id", help="增加房间机器人：房间 ID（addOnlineUsersToRoom）")
    parser.add_argument("--room-bot-total", type=int, help="增加房间机器人：在线机器人总数")
    parser.add_argument("--room-bot-on-mic", type=int, help="增加房间机器人：麦上机器人数量")

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
        area_code, mobile = normalize_mobile_login(args.query_user_by_phone, args.phone_area_code or "86")
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

    if args.diamond_query_user_id is not None and args.diamond_output == "summary":
        inner_ec, inner_em, inner_result = extract_inner_result(resp)
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            raise SystemExit(4)
        summary = parse_diamond_account_summary(args.diamond_query_user_id, inner_result)
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
    if not args.entry_url:
        print("缺少入口 URL：请传 --entry-url 或设置环境变量 MOA_ENTRY_URL", file=sys.stderr)
        return 2
    if not args.cookie:
        print("缺少 Cookie：请传 --cookie 或设置环境变量 MOA_COOKIE", file=sys.stderr)
        return 2

    _apply_optional_headers(args)
    client = MoaClient(args.entry_url, args.cookie, args.timeout_ms)

    try:
        if args.id_auth_fix_failure_user_id is not None and args.expr is None:
            return run_id_auth_fix_failure(args, client)

        if needs_family_fund_reward_setup(args):
            return run_family_fund_reward_setup(args, client)

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
