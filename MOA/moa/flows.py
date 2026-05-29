"""多步复合流程。"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .client import MoaClient, extract_ec_em_result, extract_inner_result, outer_success, parse_current_exp_from_inner
from .config import (
    family_fund_plan_by_reward_diamonds,
    build_family_exp_delta_for_level,
    build_noble_exp_delta_for_level,
    build_room_exp_delta_for_level,
    build_vip_exp_delta_for_level,
)
from .id_auth import extract_latest_id_auth_reason_list
from .family import parse_family_fund_summary, parse_family_fund_tier_set_count
from .payload import load_payload
from .time_utils import resolve_family_fund_week_key
from .vip import extract_vip_value_from_inner


def _clone_args(args: argparse.Namespace, **overrides: Any) -> argparse.Namespace:
    data = vars(args).copy()
    data.update(overrides)
    return argparse.Namespace(**data)


def build_vip_level_upgrade_payload(args: argparse.Namespace, client: MoaClient) -> dict[str, Any]:
    q_payload = load_payload(_clone_args(args, vip_query_current=True, vip_level=None, vip_exp=None))
    inner_result = client.post_expect_inner_ok(q_payload, action="查询当前 VIP 信息")
    current_vip_exp = extract_vip_value_from_inner(inner_result)
    delta = build_vip_exp_delta_for_level(args.vip_level, current_exp=current_vip_exp)
    print(
        f"已查询当前 VIP 经验值: {current_vip_exp}，目标 VIP 等级: {args.vip_level}，需要增加: {delta}",
        file=sys.stderr,
    )
    return load_payload(
        _clone_args(args, vip_current_exp=current_vip_exp, vip_exp=delta, vip_level=None, vip_query_current=False)
    )


def build_room_level_upgrade_payload(args: argparse.Namespace, client: MoaClient) -> dict[str, Any]:
    q_payload = load_payload(_clone_args(args, query_current=True, exp=None, level=None))
    inner_result = client.post_expect_inner_ok(q_payload, action="查询当前经验值")
    current_exp = parse_current_exp_from_inner(inner_result)
    delta = build_room_exp_delta_for_level(args.level, current_exp=current_exp)
    print(f"已查询当前经验值: {current_exp}，目标等级: {args.level}，需要增加: {delta}", file=sys.stderr)
    return load_payload(
        _clone_args(args, current_exp=current_exp, exp=delta, level=None, query_current=False)
    )


def build_family_level_upgrade_payload(args: argparse.Namespace, client: MoaClient) -> dict[str, Any]:
    q_payload = load_payload(_clone_args(args, family_query_current=True, family_level=None, family_exp=None))
    inner_result = client.post_expect_inner_ok(q_payload, action="查询当前家族声望值")
    current_exp = parse_current_exp_from_inner(inner_result)
    delta = build_family_exp_delta_for_level(args.family_level, current_exp=current_exp)
    print(
        f"已查询当前家族声望值: {current_exp}，目标家族等级: {args.family_level}，需要增加: {delta}",
        file=sys.stderr,
    )
    return load_payload(
        _clone_args(
            args,
            family_current_exp=current_exp,
            family_exp=delta,
            family_level=None,
            family_query_current=False,
        )
    )


def build_noble_level_upgrade_payload(args: argparse.Namespace, client: MoaClient) -> dict[str, Any]:
    raise RuntimeError("贵族月消费值暂不支持自动查询，请使用 --noble-current-exp 或 --noble-exp")


def run_id_auth_fix_failure(args: argparse.Namespace, client: MoaClient) -> int:
    q_payload = load_payload(
        _clone_args(
            args,
            id_auth_user_id=args.id_auth_fix_failure_user_id,
            id_auth_output="json",
            id_auth_delete_user_id=None,
            id_auth_reset_expire_user_id=None,
            diamond_user_id=None,
            package_gift_user_id=None,
        )
    )
    inner_result = client.post_expect_inner_ok(q_payload, action="查询认证记录")
    reason_user_ids = extract_latest_id_auth_reason_list(inner_result)
    print(
        json.dumps({"userId": str(args.id_auth_fix_failure_user_id), "reasonUserIds": reason_user_ids}, ensure_ascii=False),
        file=sys.stderr,
    )
    if not reason_user_ids:
        print("[]")
        return 0

    results: list[dict[str, Any]] = []
    for uid in reason_user_ids:
        d_payload = load_payload(
            _clone_args(
                args,
                id_auth_user_id=None,
                id_auth_reset_expire_user_id=None,
                id_auth_fix_failure_user_id=None,
                diamond_user_id=None,
                package_gift_user_id=None,
                id_auth_delete_user_id=uid,
            )
        )
        d_resp = client.post(d_payload)
        d_ec, d_em, _ = extract_ec_em_result(d_resp)
        ok_outer = outer_success(d_ec)
        ok_inner = False
        inner_err: Any = None
        try:
            d_inner_ec, d_inner_em, _ = extract_inner_result(d_resp)
            ok_inner = d_inner_ec == 0
            if not ok_inner:
                inner_err = {"ec": d_inner_ec, "em": d_inner_em}
        except RuntimeError as e:
            inner_err = str(e)

        results.append(
            {
                "deletedUserId": uid,
                "outer": {"ec": d_ec, "em": d_em, "ok": ok_outer},
                "innerOk": ok_inner,
                "innerErr": inner_err,
            }
        )

    print(json.dumps({"fixedForUserId": str(args.id_auth_fix_failure_user_id), "deletions": results}, ensure_ascii=False, indent=2))
    return 0


def run_family_fund_reward_setup(args: argparse.Namespace, client: MoaClient) -> int:
    if not args.family_id:
        raise RuntimeError("设置家族基金返奖时，必须提供 --family-id")
    plan = family_fund_plan_by_reward_diamonds(args.family_fund_reward_diamonds)
    week_key = resolve_family_fund_week_key(args.family_fund_week)
    print(
        json.dumps(
            {
                "familyId": str(args.family_id),
                "weekKey": week_key,
                "targetRewardDiamonds": plan["rewardDiamonds"],
                "targetFundTier": plan["fundTier"],
                "targetSubTier": plan["subTier"],
                "targetContribution": plan["contribution"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        file=sys.stderr,
    )

    clear_payload = load_payload(_clone_args(args, family_fund_clear=True, family_fund_reward_diamonds=None))
    client.post_expect_inner_ok(clear_payload, action="清除家族基金贡献值")

    tier_payload = load_payload(
        _clone_args(
            args,
            family_fund_tier=plan["fundTier"],
            family_fund_reward_diamonds=None,
            family_fund_clear=False,
        )
    )
    tier_result = client.post_expect_inner_ok(tier_payload, action="设置家族基金档位")
    updated = parse_family_fund_tier_set_count(tier_result)
    if updated <= 0:
        raise RuntimeError(f"家族基金档位设置失败：updated={updated}")

    contrib_payload = load_payload(
        _clone_args(
            args,
            family_fund_contrib=plan["contribution"],
            family_fund_tier=None,
            family_fund_clear=False,
            family_fund_reward_diamonds=None,
        )
    )
    client.post_expect_inner_ok(contrib_payload, action="设置家族基金贡献值")

    query_payload = load_payload(
        _clone_args(
            args,
            family_fund_contrib=0,
            family_fund_tier=None,
            family_fund_clear=False,
            family_fund_reward_diamonds=None,
        )
    )
    inner_result = client.post_expect_inner_ok(query_payload, action="查询家族基金贡献值")
    summary = parse_family_fund_summary(
        args.family_id,
        week_key,
        inner_result,
        fund_tier=plan["fundTier"],
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def needs_family_fund_reward_setup(args: argparse.Namespace) -> bool:
    return args.family_fund_reward_diamonds is not None and args.family_id is not None


def needs_vip_level_upgrade(args: argparse.Namespace) -> bool:
    return (
        args.vip_level is not None
        and args.vip_user_id is not None
        and args.vip_exp is None
        and not args.vip_query_current
        and args.expr is None
    )


def needs_family_level_upgrade(args: argparse.Namespace) -> bool:
    return (
        args.family_level is not None
        and args.family_id is not None
        and args.family_exp is None
        and not args.family_query_current
        and args.family_current_exp is None
        and args.expr is None
    )


def needs_noble_level_upgrade(args: argparse.Namespace) -> bool:
    return False


def needs_room_level_upgrade(args: argparse.Namespace) -> bool:
    return (
        args.level is not None
        and args.room_id is not None
        and args.exp is None
        and not args.query_current
        and args.expr is None
    )
