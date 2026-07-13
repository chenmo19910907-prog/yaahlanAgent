"""Payload 加载与操作路由。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from typing import Any

from .config import (
    build_family_fund_contrib_expr,
    build_family_fund_tier_set_expr,
    build_family_fund_clear_expr,
    build_room_exp_expr,
    describe_level_upgrade_plan,
    family_level_thresholds,
    member_level_thresholds,
    noble_level_thresholds,
    room_level_thresholds,
    vip_level_thresholds,
)
from .activity_gift import set_activity_mock_gift_params
from .params import (
    family_member_fund_api_value,
    set_diamond_provide_params,
    set_diamond_query_params,
    set_family_exp_params,
    set_family_decrease_exp_params,
    set_family_member_fund_contrib_params,
    set_family_leave_params,
    set_family_delete_params,
    set_family_create_time_query_params,
    set_family_members_query_params,
    set_user_joined_family_query_params,
    set_backdoor_execute_expr,
    set_id_auth_delete_person_params,
    set_id_auth_del_relation_by_scene_params,
    set_id_auth_params,
    set_id_auth_reset_expire_params,
    set_noble_params,
    set_anniversary_egg_smash_params,
    set_package_gift_params,
    set_change_user_area_params,
    normalize_cp_pair_key,
    parse_cp_pair_keys,
    set_cp_ferris_wheel_area_params,
    set_cp_ferris_wheel_tier_params,
    set_query_login_status_params,
    set_room_bot_params,
    set_room_online_params,
    set_room_member_lv_params,
    set_room_downgrade_level_params,
    set_custom_gift_reset_expire_params,
    set_custom_gift_rank_active_params,
    set_custom_gift_rank_delete_params,
    custom_gift_rank_defaults,
    set_vip_del_params,
    set_vip_info_query_params,
    set_vip_params,
    set_vip_try_dispatch_params,
    set_user_prop_query_params,
    set_user_follow_params,
)
from .time_utils import resolve_expire_ms, resolve_family_fund_week_key
from .user_area import describe_user_area, normalize_user_area
from .user_login import normalize_mobile_login, resolve_phone_area_code
from .wealth_charm import build_wealth_charm_query_expr

PayloadBuilder = Callable[[argparse.Namespace, dict[str, Any]], None]


def _ensure_settings(payload: dict[str, Any]) -> dict[str, Any]:
    settings = payload.get("settings")
    if settings is None:
        settings = {}
        payload["settings"] = settings
    if not isinstance(settings, dict):
        raise ValueError("payload.settings 必须是 object")
    return settings


def apply_top_level_overrides(payload: dict[str, Any], args: argparse.Namespace) -> None:
    for arg_name, key in (
        ("service_url", "url"),
        ("moa_method", "method"),
        ("region", "region"),
        ("env", "env"),
        ("cluster", "cluster"),
        ("server", "server"),
        ("momo_id", "momoId"),
        ("momo_name", "momoName"),
        ("header", "header"),
    ):
        value = getattr(args, arg_name, None)
        if value is not None:
            payload[key] = value

    if getattr(args, "host", None) is not None:
        _ensure_settings(payload)["host"] = args.host
    if getattr(args, "moa_time", None) is not None:
        _ensure_settings(payload)["time"] = str(args.moa_time)
    if getattr(args, "group", None) is not None:
        _ensure_settings(payload)["group"] = args.group
    if getattr(args, "header_type", None) is not None:
        _ensure_settings(payload)["headerType"] = args.header_type


def _apply_room_expr(payload: dict[str, Any], args: argparse.Namespace) -> None:
    expr: str | None = None
    if args.expr is not None:
        expr = args.expr
    elif args.room_id is not None:
        if args.query_current:
            expr = build_room_exp_expr(args.room_id, 0)
        elif args.exp is not None:
            expr = build_room_exp_expr(args.room_id, args.exp)
        elif args.level is not None:
            current = args.current_exp if args.current_exp is not None else 0
            delta, _, message = describe_level_upgrade_plan(
                level=args.level,
                current_exp=current,
                thresholds=room_level_thresholds(),
                label="房间",
                mode=args.level_exp_mode,
            )
            print(message, file=sys.stderr)
            expr = build_room_exp_expr(args.room_id, delta)
        else:
            raise ValueError("提供了 --room-id 时，必须同时提供 --exp 或 --level 或 --query-current")
    elif args.exp is not None or args.level is not None:
        raise ValueError("使用 --exp/--level 时必须提供 --room-id")

    if expr is None:
        return

    params = payload.get("params")
    if not isinstance(params, list) or not params or not isinstance(params[0], dict):
        raise ValueError("payload.params 必须是非空数组，才能覆盖 params[0].value/txt")
    params[0]["value"] = expr
    params[0]["txt"] = expr


def _op_id_auth_query(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/internal/user/id-auth-api"
    payload["method"] = "queryRealPersonRecord"
    set_id_auth_params(payload, user_id=args.id_auth_user_id)


def _op_id_auth_reset_expire(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/internal/user/id-auth-api"
    payload["method"] = "resetRelationPersonExpireTime"
    expire_ms = resolve_expire_ms(expire_ms=args.id_auth_expire_ms, expire_at=args.id_auth_expire_at)
    set_id_auth_reset_expire_params(payload, user_id=args.id_auth_reset_expire_user_id, expire_ms=expire_ms)


def _op_id_auth_del_relation_by_scene(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    if not args.id_auth_relation_scene:
        raise ValueError(
            "按场景删除真人认证须指定 --id-auth-relation-scene（DEALER=币商，ANCHOR=普通/主播）"
        )
    payload["url"] = "/service/internal/user/id-auth-api"
    payload["method"] = "delRelationPersonInfoByScene"
    set_id_auth_del_relation_by_scene_params(
        payload,
        user_id=args.id_auth_del_relation_user_id,
        scene=args.id_auth_relation_scene,
    )


def _op_id_auth_delete(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/internal/user/id-auth-api"
    payload["method"] = "internalAuthDeletePerson"
    set_id_auth_delete_person_params(payload, user_id=args.id_auth_delete_user_id)


def _op_vip_del(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/voga-mts-user-vip-stage"
    payload["method"] = "delVipInfo"
    set_vip_del_params(payload, user_id=args.vip_del_user_id)


def _vip_try_mode(args: argparse.Namespace) -> bool:
    return args.vip_try_user_id is not None


def _op_vip_try_dispatch(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/voga-mts-user-vip-stage"
    if args.vip_try_level is None or args.vip_try_duration_seconds is None:
        raise ValueError("下发 VIP 体验卡时，必须同时提供 --vip-try-level 与 --vip-try-duration-seconds")
    set_vip_try_dispatch_params(
        payload,
        user_id=args.vip_try_user_id,
        try_level=args.vip_try_level,
        duration_seconds=args.vip_try_duration_seconds,
    )


def _op_custom_gift_reset_expire(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    set_custom_gift_reset_expire_params(payload, user_id=args.custom_gift_reset_user_id)


def _custom_gift_rank_add_mode(args: argparse.Namespace) -> bool:
    return args.custom_gift_rank_gift_id is not None and not args.custom_gift_rank_delete


def _custom_gift_rank_delete_mode(args: argparse.Namespace) -> bool:
    return args.custom_gift_rank_gift_id is not None and args.custom_gift_rank_delete


def _op_custom_gift_rank_delete(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    defaults = custom_gift_rank_defaults()
    area = args.custom_gift_rank_area or defaults.get("defaultArea", "MENA")
    set_custom_gift_rank_delete_params(
        payload,
        area=str(area),
        gift_id=args.custom_gift_rank_gift_id,
    )
    print(
        f"清除定制礼物榜单：giftId={args.custom_gift_rank_gift_id} area={area}",
        file=sys.stderr,
    )


def _op_custom_gift_rank_active(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    if args.custom_gift_rank_active_value is None:
        raise ValueError("必须提供 --custom-gift-rank-active-value（活跃值增量）")
    defaults = custom_gift_rank_defaults()
    period = args.custom_gift_rank_period or defaults.get("defaultPeriod", "PRE")
    area = args.custom_gift_rank_area or defaults.get("defaultArea", "MENA")
    user_id = args.custom_gift_rank_user_id or defaults.get("defaultUserId", "")
    set_custom_gift_rank_active_params(
        payload,
        period=str(period),
        area=str(area),
        gift_id=args.custom_gift_rank_gift_id,
        active_value=args.custom_gift_rank_active_value,
        user_id=str(user_id),
    )
    print(
        f"定制礼物榜单活跃值：giftId={args.custom_gift_rank_gift_id} +{args.custom_gift_rank_active_value} "
        f"period={period} area={area}",
        file=sys.stderr,
    )


def _cp_ferris_tier_mode(args: argparse.Namespace) -> bool:
    return args.cp_ferris_tier is not None


def _cp_ferris_area_mode(args: argparse.Namespace) -> bool:
    return args.cp_ferris_area is not None


def _op_cp_ferris_tier(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    pair_keys: list[str] = []
    if args.cp_pairs:
        pair_keys.extend(parse_cp_pair_keys(args.cp_pairs))
    if args.cp_pair_left is not None and args.cp_pair_right is not None:
        pair_keys.append(normalize_cp_pair_key(args.cp_pair_left, args.cp_pair_right))
    if not pair_keys:
        raise ValueError("设置 CP 档位需提供 --cp-pairs 或同时提供 --cp-pair-left 与 --cp-pair-right")
    set_cp_ferris_wheel_tier_params(payload, tier=args.cp_ferris_tier, pair_keys=pair_keys)


def _op_cp_ferris_area(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    set_cp_ferris_wheel_area_params(payload, args.cp_ferris_area)


def _op_change_user_area(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/yaahlan/components/callback/user-area"
    payload["method"] = "changeAreaForTest"
    area = normalize_user_area(args.user_area)
    set_change_user_area_params(payload, user_id=args.change_user_area_user_id, area_code=area)
    meta = describe_user_area(area)
    print(
        f"切换用户 {args.change_user_area_user_id} 大区为 {area}（{meta['name']}，{meta['time_label']} {meta['timezone']}）",
        file=sys.stderr,
    )
    if meta.get("note"):
        print(f"  说明: {meta['note']}", file=sys.stderr)


def _op_query_user_by_phone(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/yaahlan/mdp-user-login"
    payload["method"] = "queryLoginStatusV2"
    area_code, mobile = normalize_mobile_login(args.query_user_by_phone, resolve_phone_area_code(args))
    set_query_login_status_params(
        payload,
        area_code=area_code,
        mobile=mobile,
        app_id=args.phone_app_id,
    )


def _op_cancel_user(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    """注销账号（voga-mts-user-backdoor execute；userCancelService.cancelUserReal）。"""
    payload["url"] = "/service/voga-mts-user-backdoor"
    payload["method"] = "execute"
    user_id = str(args.cancel_user_id).strip()
    if not user_id:
        raise ValueError("注销账号时 userId 不能为空")
    expr = f'context.getBean("userCancelService").cancelUserReal("{user_id}")'
    print(f"注销账号 userId={user_id}", file=sys.stderr)
    set_backdoor_execute_expr(payload, expr)


def _op_charm_query(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    """查询魅力等级（voga-mts-user-backdoor execute；getCharmInfoNoAvatar）。"""
    payload["url"] = "/service/voga-mts-user-backdoor"
    payload["method"] = "execute"
    expr = build_wealth_charm_query_expr("getCharmInfoNoAvatar", args.charm_query_user_id)
    set_backdoor_execute_expr(payload, expr)


def _op_wealth_query(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    """查询财富等级（voga-mts-user-backdoor execute；getWealthInfoNoAvatar）。"""
    payload["url"] = "/service/voga-mts-user-backdoor"
    payload["method"] = "execute"
    expr = build_wealth_charm_query_expr("getWealthInfoNoAvatar", args.wealth_query_user_id)
    set_backdoor_execute_expr(payload, expr)


def _op_user_prop_query(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/mdp-prop/user-prop-api-service-test"
    payload["method"] = "queryOwnPropList"
    if args.user_prop_type_code is None:
        raise ValueError("查询用户装扮时必须提供 --user-prop-type-code")
    set_user_prop_query_params(
        payload,
        user_id=args.user_prop_query_user_id,
        prop_type_code=args.user_prop_type_code,
        lang=args.user_prop_lang,
        app_id=args.user_prop_app_id,
    )


def _op_diamond_query(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/voga-base-service-middle-pay-stage"
    payload["method"] = "queryUserAccount"
    set_diamond_query_params(payload, user_id=args.diamond_query_user_id)


def _op_diamond(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/voga-base-service-middle-pay-stage"
    payload["method"] = "provideDiamond"
    if args.diamond_num is None:
        raise ValueError("必须提供 --diamond-num（钻石数量）")
    set_diamond_provide_params(payload, user_id=args.diamond_user_id, num=args.diamond_num)


def _member_lv_mode(args: argparse.Namespace) -> bool:
    return args.member_lv_room_id is not None and args.member_lv_user_id is not None


def _op_room_member_lv(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/room/internal/room-user-active-stage"
    payload["method"] = "doorIncrMemberLv"

    if args.member_lv_exp is not None:
        set_room_member_lv_params(payload, args.member_lv_room_id, args.member_lv_user_id, exp_delta=args.member_lv_exp)
        return
    if args.member_lv_level is not None:
        current = args.member_lv_current_exp if args.member_lv_current_exp is not None else 0
        delta, _, message = describe_level_upgrade_plan(
            level=args.member_lv_level,
            current_exp=current,
            thresholds=member_level_thresholds(),
            label="房间成员",
            mode=args.level_exp_mode,
        )
        print(message, file=sys.stderr)
        set_room_member_lv_params(payload, args.member_lv_room_id, args.member_lv_user_id, exp_delta=delta)
        return
    raise ValueError(
        "提供了 --member-lv-room-id 与 --member-lv-user-id 时，"
        "必须同时提供 --member-lv-exp 或 --member-lv-level"
    )


def _room_set_level_mode(args: argparse.Namespace) -> bool:
    return args.room_set_level_room_id is not None


def _op_room_set_level(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    if args.room_set_level is None:
        raise ValueError("设置房间等级时，必须提供 --room-set-level")
    set_room_downgrade_level_params(
        payload,
        room_id=args.room_set_level_room_id,
        level=args.room_set_level,
    )


def _op_user_rank_dispatch(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    area = (args.user_rank_area or "MENA").upper()
    time_type = (args.user_rank_time_type or "WEEK").upper()
    cycle = (args.user_rank_cycle or "NOW").upper()
    # MONTH 使用 V2 方法，WEEK/DAY 使用原方法
    method_name = "dispatchTotalUserRankListPrizeV2" if time_type == "MONTH" else "dispatchTotalUserRankListPrize"
    expr = (
        f'context.getBean("roomGiftRankListServiceImpl")'
        f".{method_name}("
        f"com.immomo.voga.mts.room.api.enums.rank.RoomGiftRankListTimeTypeEnum.{time_type},"
        f"com.immomo.voga.mts.room.api.enums.rank.RoomGiftRankListCycleEnum.{cycle},"
        f"com.immomo.yaahlan.business.utils.enums.AreaEnum.{area})"
    )
    payload["url"] = "/service/voga-mts-room-backdoor"
    payload["method"] = "execute"
    params = payload.get("params")
    if not isinstance(params, list) or not params or not isinstance(params[0], dict):
        raise ValueError("payload.params 必须是非空数组，才能覆盖 params[0].value/txt")
    params[0]["value"] = expr
    params[0]["txt"] = expr
    print(f"用户榜单奖励下发：method={method_name} timeType={time_type} cycle={cycle} area={area}", file=sys.stderr)


def _op_contrib_day_rank_dispatch(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    area = (args.contrib_day_rank_area or "MENA").upper()
    expr = (
        f'context.getBean("roomGiftRankListServiceImpl")'
        f".dispatchTotalContributionRankListPrizeV2("
        f"1,com.immomo.yaahlan.business.utils.enums.AreaEnum.{area})"
    )
    payload["url"] = "/service/voga-mts-room-backdoor"
    payload["method"] = "execute"
    params = payload.get("params")
    if not isinstance(params, list) or not params or not isinstance(params[0], dict):
        raise ValueError("payload.params 必须是非空数组，才能覆盖 params[0].value/txt")
    params[0]["value"] = expr
    params[0]["txt"] = expr
    print(f"贡献日榜奖励下发：area={area}", file=sys.stderr)


def _op_charm_day_rank_dispatch(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    area = (args.charm_day_rank_area or "MENA").upper()
    expr = (
        f'context.getBean("roomGiftRankListServiceImpl")'
        f".dispatchTotalCharmRankListPrizeV2("
        f"1,com.immomo.yaahlan.business.utils.enums.AreaEnum.{area})"
    )
    payload["url"] = "/service/voga-mts-room-backdoor"
    payload["method"] = "execute"
    params = payload.get("params")
    if not isinstance(params, list) or not params or not isinstance(params[0], dict):
        raise ValueError("payload.params 必须是非空数组，才能覆盖 params[0].value/txt")
    params[0]["value"] = expr
    params[0]["txt"] = expr
    print(f"魅力日榜奖励下发：area={area}", file=sys.stderr)


def _op_room_day_rank_dispatch(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    area = (args.room_day_rank_area or "MENA").upper()
    expr = (
        f'context.getBean("roomGiftRankListServiceImpl")'
        f".dispatchTotalRoomDayRankListPrize("
        f"com.immomo.yaahlan.business.utils.enums.AreaEnum.{area})"
    )
    payload["url"] = "/service/voga-mts-room-backdoor"
    payload["method"] = "execute"
    params = payload.get("params")
    if not isinstance(params, list) or not params or not isinstance(params[0], dict):
        raise ValueError("payload.params 必须是非空数组，才能覆盖 params[0].value/txt")
    params[0]["value"] = expr
    params[0]["txt"] = expr
    print(f"房间日榜奖励下发：area={area}", file=sys.stderr)


def _op_find_ip(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/pip-new-search-service"
    payload["method"] = "findIp"
    params = payload.get("params")
    if not isinstance(params, list) or not params or not isinstance(params[0], dict):
        raise ValueError("payload.params 必须是非空数组，才能覆盖 params[0].value/txt")
    params[0]["value"] = args.find_ip
    params[0]["txt"] = args.find_ip
    print(f"查询 IP 归属地：ip={args.find_ip}", file=sys.stderr)


def _op_user_home_country_update(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    if args.user_home_country is None:
        raise ValueError("修改注册国家时，必须同时提供 --user-home-country")
    country = args.user_home_country.upper()
    payload["url"] = "/service/mdp-user-service"
    payload["method"] = "updateUser"
    new_value: dict[str, Any] = {"appId": 2005, "userId": args.user_home_country_user_id, "homeCountry": country}
    params = payload.get("params")
    if not isinstance(params, list) or not params or not isinstance(params[0], dict):
        raise ValueError("payload.params 必须是非空数组，才能覆盖 params[0].value/txt")
    params[0]["value"] = new_value
    params[0]["json"] = json.dumps(new_value, ensure_ascii=False)
    params[0]["txt"] = json.dumps(new_value, ensure_ascii=False)
    params[0]["type"] = "json"
    print(f"修改用户注册国家：userId={args.user_home_country_user_id} homeCountry={country}", file=sys.stderr)


def _op_user_set_reg_time(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    if args.user_set_reg_time_at is None:
        raise ValueError("设置注册时间时，必须同时提供 --user-set-reg-time-at")
    # 支持直接传毫秒时间戳或自然语言日期
    raw = args.user_set_reg_time_at.strip()
    if re.fullmatch(r"\d{13}", raw):
        ts_ms = int(raw)
    else:
        ts_ms = resolve_expire_ms(expire_at=raw)
    expr = f'context.getBean("userVipTaskDao").saveUserRegTime("{args.user_set_reg_time_user_id}",{ts_ms}L)'
    payload["url"] = "/service/voga-mts-user-backdoor"
    payload["method"] = "execute"
    params = payload.get("params")
    if not isinstance(params, list) or not params or not isinstance(params[0], dict):
        raise ValueError("payload.params 必须是非空数组，才能覆盖 params[0].value/txt")
    params[0]["value"] = expr
    params[0]["txt"] = expr
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _ZoneInfo
    dt_str = _dt.fromtimestamp(ts_ms / 1000, tz=_ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
    print(f"设置用户注册时间：userId={args.user_set_reg_time_user_id} ts={ts_ms}（{dt_str}）", file=sys.stderr)


def _op_user_reg_time_query(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    expr = f'context.getBean("userVipTaskDao").getUserRegTime("{args.user_reg_time_user_id}")'
    payload["url"] = "/service/voga-mts-user-backdoor"
    payload["method"] = "execute"
    params = payload.get("params")
    if not isinstance(params, list) or not params or not isinstance(params[0], dict):
        raise ValueError("payload.params 必须是非空数组，才能覆盖 params[0].value/txt")
    params[0]["value"] = expr
    params[0]["txt"] = expr
    print(f"查询用户注册时间：userId={args.user_reg_time_user_id}", file=sys.stderr)


def _op_pk_rank_settle(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    offset = args.pk_rank_settle_week_offset  # 0=本周，-1=上周
    payload["url"] = "/service/room/internal/room-pk"
    payload["method"] = "calculateAndDistributeWeekPrize"
    params = payload.get("params")
    if not isinstance(params, list) or not params or not isinstance(params[0], dict):
        raise ValueError("payload.params 必须是非空数组，才能覆盖 params[0].value/txt")
    params[0]["value"] = str(offset)
    params[0]["txt"] = str(offset)
    params[0]["type"] = "int"
    label = "本周" if offset == 0 else (f"上周" if offset == -1 else f"偏移{offset}周")
    print(f"PK榜周结算发奖：weekOffset={offset}（{label}）", file=sys.stderr)


def _op_pk_rank_query(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    # 复用 family fund week key 逻辑，去掉连字符得到 YYYYMMDDweek 格式
    raw_key = resolve_family_fund_week_key(args.pk_rank_query_week)  # -> "YYYYMMDD-week"
    week_part = raw_key.replace("-", "")  # -> "YYYYMMDDweek"
    redis_key = f"new:pk:week:rank:record:{week_part}"
    expr = f'context.getBean("roomClusterDao").get("1","{redis_key}")'
    payload["url"] = "/service/voga-mts-room-backdoor"
    payload["method"] = "execute"
    params = payload.get("params")
    if not isinstance(params, list) or not params or not isinstance(params[0], dict):
        raise ValueError("payload.params 必须是非空数组，才能覆盖 params[0].value/txt")
    params[0]["value"] = expr
    params[0]["txt"] = expr
    print(f"PK榜查询数值：redisKey={redis_key}", file=sys.stderr)


def _op_pk_rank_add(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    if args.pk_rank_value is None:
        raise ValueError("增加 PK 榜值时，必须同时提供 --pk-rank-value")
    expr = f'context.getBean("pkRankService").handlePkRank("{args.pk_rank_user_id}",{args.pk_rank_value},"123",2)'
    payload["url"] = "/service/voga-mts-room-backdoor"
    payload["method"] = "execute"
    params = payload.get("params")
    if not isinstance(params, list) or not params or not isinstance(params[0], dict):
        raise ValueError("payload.params 必须是非空数组，才能覆盖 params[0].value/txt")
    params[0]["value"] = expr
    params[0]["txt"] = expr
    print(f"PK榜增加PK值：userId={args.pk_rank_user_id} value={args.pk_rank_value}", file=sys.stderr)


def _op_room_add_bots(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/room/internal/room-test-stage"
    payload["method"] = "addOnlineUsersToRoom"
    if args.room_bot_total is None or args.room_bot_on_mic is None:
        raise ValueError("增加房间机器人时，必须同时提供 --room-bot-total 与 --room-bot-on-mic")
    set_room_bot_params(
        payload,
        room_id=args.room_bot_room_id,
        total_bots=args.room_bot_total,
        on_mic_bots=args.room_bot_on_mic,
    )


def _op_room_online(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    room_id = str(args.room_online_room_id).strip()
    if not room_id:
        raise ValueError("增加房间在线人数：--room-online-room-id 不能为空")
    payload["url"] = "/service/room/internal/room-test-stage"
    payload["method"] = "addOnlineUsersToRoom"
    entry_limit = args.room_online_limit if args.room_online_limit is not None else 0
    auto_mic = args.room_online_mic if args.room_online_mic is not None else 0
    set_room_online_params(payload, room_id=room_id, entry_limit=entry_limit, auto_mic=auto_mic)
    print(
        f"增加房间在线人数：roomId={room_id} 进房上限={entry_limit}(0=不限) 自动上麦={auto_mic}(0=无)",
        file=sys.stderr,
    )


def _op_package_gift(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/voga-base-service-middle-gift-stage"
    payload["method"] = "addPackageGift"
    set_package_gift_params(
        payload,
        user_id=args.package_gift_user_id,
        product_num=args.package_gift_num,
        give_user_id=args.package_gift_give_user_id or "",
    )


def _anniversary_egg_mode(args: argparse.Namespace) -> bool:
    return (
        args.anniversary_egg_user_id is not None
        or args.anniversary_egg_room_id is not None
        or args.anniversary_egg_smash_count is not None
        or getattr(args, "anniversary_egg_remaining", None) is not None
    )


def _op_anniversary_egg_smash(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    if not args.anniversary_egg_user_id:
        raise ValueError("3周年砸金蛋需提供 --anniversary-egg-user-id")
    from .anniversary_egg import get_remain_chance, resolve_own_room_id
    from .params import resolve_anniversary_egg_batch_count

    lang = getattr(args, "anniversary_egg_lang", None) or "en"
    room_id = (args.anniversary_egg_room_id or "").strip()
    if not room_id:
        room_id = resolve_own_room_id(args.anniversary_egg_user_id)
        args.anniversary_egg_room_id = room_id
        print(f"未传房间，默认自己的房间 roomId={room_id}", file=sys.stderr)

    remaining = getattr(args, "anniversary_egg_remaining", None)
    if remaining is None:
        try:
            remaining = get_remain_chance(args.anniversary_egg_user_id, room_id)
            print(f"当前剩余砸蛋次数 remain={remaining}", file=sys.stderr)
        except (RuntimeError, ValueError) as exc:
            print(f"查询剩余次数失败（仍继续砸蛋）: {exc}", file=sys.stderr)

    expected = resolve_anniversary_egg_batch_count(
        remaining=remaining,
        explicit_count=args.anniversary_egg_smash_count,
    )
    set_anniversary_egg_smash_params(
        payload,
        user_id=args.anniversary_egg_user_id,
        room_id=room_id,
        smash_count=args.anniversary_egg_smash_count,
        remaining=remaining,
        lang=lang,
    )
    print(
        f"3周年砸金蛋：userId={args.anniversary_egg_user_id} roomId={room_id} "
        f"lang={lang} 期望本批≈{expected}（实际次数以返回值/剩余差值为准）",
        file=sys.stderr,
    )


def _family_decrease_mode(args: argparse.Namespace) -> bool:
    return args.family_id is not None and args.family_decrease_exp is not None


def _family_fund_tier_mode(args: argparse.Namespace) -> bool:
    return args.family_fund_tier is not None


def _family_fund_contrib_mode(args: argparse.Namespace) -> bool:
    return args.family_fund_contrib is not None


def _family_fund_clear_mode(args: argparse.Namespace) -> bool:
    return args.family_fund_clear


def _family_member_fund_contrib_mode(args: argparse.Namespace) -> bool:
    return args.family_member_fund_user_id is not None and args.family_member_fund_contrib is not None


def _family_query_members_mode(args: argparse.Namespace) -> bool:
    return bool(args.family_query_members)


def _family_query_create_time_mode(args: argparse.Namespace) -> bool:
    return bool(args.family_query_create_time)


def _family_delete_mode(args: argparse.Namespace) -> bool:
    return bool(args.family_delete)


def _family_query_joined_mode(args: argparse.Namespace) -> bool:
    return args.family_query_joined_user_id is not None


def _family_add_mode(args: argparse.Namespace) -> bool:
    return (
        args.family_id is not None
        and not _family_decrease_mode(args)
        and not _family_fund_tier_mode(args)
        and not _family_fund_contrib_mode(args)
        and not _family_fund_clear_mode(args)
        and not _family_member_fund_contrib_mode(args)
        and not _family_query_members_mode(args)
        and not _family_query_create_time_mode(args)
        and not _family_delete_mode(args)
    )


def _op_family_query_members(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/internal/user/family-moa"
    payload["method"] = "getFamilyMembers"
    if not args.family_id:
        raise ValueError("查询家族成员时，必须提供 --family-id")
    set_family_members_query_params(payload, args.family_id)


def _op_family_query_create_time(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/internal/user/family-moa"
    payload["method"] = "getFamilyCreateTime"
    if not args.family_id:
        raise ValueError("查询家族创建时间时，必须提供 --family-id")
    set_family_create_time_query_params(payload, args.family_id)


def _op_family_query_joined(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/internal/user/family-moa"
    payload["method"] = "getUserJoinedFamily"
    set_user_joined_family_query_params(payload, args.family_query_joined_user_id)


def _op_family_leave(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/external/user/family-api"
    payload["method"] = "leave"
    user_id = str(args.family_leave_user_id).strip()
    if not user_id:
        raise ValueError("移除家族成员时 userId 不能为空")
    print(f"移除家族成员 userId={user_id}", file=sys.stderr)
    set_family_leave_params(payload, user_id)


def _op_family_delete(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/external/user/family-api"
    payload["method"] = "deleteFamily"
    if not args.family_id:
        raise ValueError("解散家族时，必须提供 --family-id")
    owner_user_id = str(args.family_delete_owner_id or "").strip()
    if not owner_user_id:
        raise ValueError("解散家族时，必须提供 --family-delete-owner-id（族长 userId）")
    print(f"解散家族 familyId={args.family_id} ownerUserId={owner_user_id}", file=sys.stderr)
    set_family_delete_params(payload, args.family_id, owner_user_id)


def _op_user_follow(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    uid = str(args.follow_uid or "").strip()
    remote_uid = str(args.follow_remote_uid or "").strip()
    if not uid or not remote_uid:
        raise ValueError("关注好友须同时提供 --follow-uid 与 --follow-remote-uid")
    if uid == remote_uid:
        raise ValueError("uid 与 remoteUid 不能相同")
    if args.follow_mutual:
        raise ValueError("互关成为好友请直接执行 --follow-mutual（会连续调用两次 addUserRelation）")
    print(f"关注: {uid} -> {remote_uid}", file=sys.stderr)
    set_user_follow_params(payload, uid, remote_uid)


def _op_family_member_fund_contrib(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/internal/user/family-moa"
    payload["method"] = "batchIncrFundContribution"
    if not args.family_id:
        raise ValueError("给成员增加家族基金贡献值时，必须提供 --family-id")
    week_key = resolve_family_fund_week_key(args.family_fund_week)
    user_id = str(args.family_member_fund_user_id).strip()
    contrib = args.family_member_fund_contrib
    api_value = family_member_fund_api_value(contrib)
    print(
        f"成员 {user_id} 增加家族基金贡献值 {contrib}，周期: {week_key}（API 传值 {api_value}）",
        file=sys.stderr,
    )
    set_family_member_fund_contrib_params(
        payload,
        family_id=args.family_id,
        week_key=week_key,
        user_contributions={user_id: contrib},
    )


def _op_family_fund_clear(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/voga-mts-user-backdoor"
    payload["method"] = "execute"
    if not args.family_id:
        raise ValueError("清除家族基金贡献值时，必须提供 --family-id")
    week_offset = 0 if args.family_fund_week_offset is None else args.family_fund_week_offset
    week_label = "本周" if week_offset == 0 else ("上周" if week_offset == -1 else f"偏移 {week_offset} 周")
    expr = build_family_fund_clear_expr(args.family_id, week_offset)
    print(f"清除家族基金贡献值: {week_label}（week_offset={week_offset}）", file=sys.stderr)
    set_backdoor_execute_expr(payload, expr)


def _op_family_fund_contrib(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/voga-mts-user-backdoor"
    payload["method"] = "execute"
    if not args.family_id:
        raise ValueError("家族基金贡献值操作时，必须提供 --family-id")
    week_key = resolve_family_fund_week_key(args.family_fund_week)
    expr = build_family_fund_contrib_expr(args.family_id, args.family_fund_contrib, week_key)
    if args.family_fund_contrib == 0:
        print(f"查询家族基金贡献值，周期: {week_key}", file=sys.stderr)
    else:
        print(f"家族基金周期: {week_key}", file=sys.stderr)
    set_backdoor_execute_expr(payload, expr)


def _op_family_fund_tier(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/voga-mts-user-backdoor"
    payload["method"] = "execute"
    family_ids = args.family_fund_ids if args.family_fund_ids else args.family_id
    if not family_ids:
        raise ValueError("设置家族基金档位时，必须提供 --family-id 或 --family-fund-ids")
    if isinstance(family_ids, str):
        ids = [item.strip() for item in family_ids.split(",") if item.strip()]
    else:
        ids = [str(item).strip() for item in family_ids if str(item).strip()]
    flag = 0 if args.family_fund_tier_flag is None else args.family_fund_tier_flag
    expr = build_family_fund_tier_set_expr(ids, args.family_fund_tier, flag)
    print(f"设置家族基金档位: {args.family_fund_tier}，家族: {','.join(ids)}，flag={flag}", file=sys.stderr)
    set_backdoor_execute_expr(payload, expr)


def _op_family_decrease_exp(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/internal/user/family-moa"
    payload["method"] = "decreaseFamilyActiveValue"
    set_family_decrease_exp_params(payload, family_id=args.family_id, decrease_exp=args.family_decrease_exp)


def _op_family_exp(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/internal/user/family-moa"
    payload["method"] = "addFamilyActiveValueBySystem"

    if args.family_query_current:
        set_family_exp_params(payload, family_id=args.family_id, exp_delta=0)
        return
    if args.family_exp is not None:
        set_family_exp_params(payload, family_id=args.family_id, exp_delta=args.family_exp)
        return
    if args.family_level is not None:
        current = args.family_current_exp if args.family_current_exp is not None else 0
        delta, _, message = describe_level_upgrade_plan(
            level=args.family_level,
            current_exp=current,
            thresholds=family_level_thresholds(),
            label="家族",
            mode=args.level_exp_mode,
        )
        print(message, file=sys.stderr)
        set_family_exp_params(payload, family_id=args.family_id, exp_delta=delta)
        return
    raise ValueError("提供了 --family-id 时，必须同时提供 --family-exp、--family-level 或 --family-query-current")


def _op_noble(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload["url"] = "/service/voga-mts-user-wealth-charm-level-stage"
    payload["method"] = "incrNobelLevel"

    if args.noble_exp is not None:
        set_noble_params(payload, user_id=args.noble_user_id, noble_exp_delta=args.noble_exp)
        return
    if args.noble_level is not None:
        current = args.noble_current_exp if args.noble_current_exp is not None else 0
        delta, _, message = describe_level_upgrade_plan(
            level=args.noble_level,
            current_exp=current,
            thresholds=noble_level_thresholds(),
            label="贵族",
            mode=args.level_exp_mode,
        )
        print(message, file=sys.stderr)
        set_noble_params(payload, user_id=args.noble_user_id, noble_exp_delta=delta)
        return
    raise ValueError("提供了 --noble-user-id 时，必须同时提供 --noble-exp 或 --noble-level")


def _op_vip(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    payload.setdefault("url", "/service/voga-mts-user-vip-stage")
    payload.setdefault("method", "addVipValue")

    if args.vip_query_current:
        set_vip_info_query_params(payload, user_id=args.vip_user_id)
        return
    if args.vip_exp is not None:
        if args.vip_exp < 0:
            raise ValueError("vip_exp 不能为负数")
        set_vip_params(payload, user_id=args.vip_user_id, vip_exp_delta=args.vip_exp)
        return
    if args.vip_level is not None:
        current = args.vip_current_exp if args.vip_current_exp is not None else 0
        delta, _, message = describe_level_upgrade_plan(
            level=args.vip_level,
            current_exp=current,
            thresholds=vip_level_thresholds(),
            label="VIP",
            mode=args.level_exp_mode,
        )
        print(message, file=sys.stderr)
        set_vip_params(payload, user_id=args.vip_user_id, vip_exp_delta=delta)
        return
    raise ValueError("提供了 --vip-user-id 时，必须同时提供 --vip-exp 或 --vip-level 或 --vip-query-current")


def _op_activity_mock_gift(args: argparse.Namespace, payload: dict[str, Any]) -> None:
    if not args.activity_gift_to_user_id:
        raise ValueError("活动模拟送礼需提供 --activity-gift-to-user-id")
    method = args.activity_gift_method or args.moa_method
    set_activity_mock_gift_params(
        payload,
        args.activity_gift_from_user_id,
        args.activity_gift_to_user_id,
        flag=args.activity_gift_flag,
        method=method,
        product_id=args.activity_gift_product_id,
        product_num=args.activity_gift_product_num,
        price=args.activity_gift_price,
        real_fee=args.activity_gift_real_fee,
        total_fee=args.activity_gift_total_fee,
        room_id=args.activity_gift_room_id or "",
    )


# (predicate, handler) — 按优先级匹配首个操作
OPERATIONS: list[tuple[Callable[[argparse.Namespace], bool], PayloadBuilder]] = [
    (lambda a: a.activity_gift_from_user_id is not None, _op_activity_mock_gift),
    (lambda a: _cp_ferris_tier_mode(a), _op_cp_ferris_tier),
    (lambda a: _cp_ferris_area_mode(a), _op_cp_ferris_area),
    (lambda a: a.change_user_area_user_id is not None, _op_change_user_area),
    (lambda a: a.cancel_user_id is not None, _op_cancel_user),
    (lambda a: a.charm_query_user_id is not None, _op_charm_query),
    (lambda a: a.wealth_query_user_id is not None, _op_wealth_query),
    (lambda a: a.query_user_by_phone is not None, _op_query_user_by_phone),
    (lambda a: a.id_auth_user_id is not None, _op_id_auth_query),
    (lambda a: a.id_auth_reset_expire_user_id is not None, _op_id_auth_reset_expire),
    (lambda a: a.id_auth_del_relation_user_id is not None, _op_id_auth_del_relation_by_scene),
    (lambda a: a.id_auth_delete_user_id is not None, _op_id_auth_delete),
    (lambda a: a.vip_del_user_id is not None, _op_vip_del),
    (lambda a: _vip_try_mode(a), _op_vip_try_dispatch),
    (lambda a: a.custom_gift_reset_user_id is not None, _op_custom_gift_reset_expire),
    (lambda a: _custom_gift_rank_delete_mode(a), _op_custom_gift_rank_delete),
    (lambda a: _custom_gift_rank_add_mode(a), _op_custom_gift_rank_active),
    (lambda a: a.user_prop_query_user_id is not None, _op_user_prop_query),
    (lambda a: a.diamond_query_user_id is not None, _op_diamond_query),
    (lambda a: a.diamond_user_id is not None, _op_diamond),
    (lambda a: _room_set_level_mode(a), _op_room_set_level),
    (lambda a: a.user_rank_area is not None, _op_user_rank_dispatch),
    (lambda a: a.contrib_day_rank_area is not None, _op_contrib_day_rank_dispatch),
    (lambda a: a.charm_day_rank_area is not None, _op_charm_day_rank_dispatch),
    (lambda a: a.room_day_rank_area is not None, _op_room_day_rank_dispatch),
    (lambda a: a.find_ip is not None, _op_find_ip),
    (lambda a: a.user_home_country_user_id is not None, _op_user_home_country_update),
    (lambda a: a.user_set_reg_time_user_id is not None, _op_user_set_reg_time),
    (lambda a: a.user_reg_time_user_id is not None, _op_user_reg_time_query),
    (lambda a: a.pk_rank_settle_week_offset is not None, _op_pk_rank_settle),
    (lambda a: a.pk_rank_query_week is not None, _op_pk_rank_query),
    (lambda a: a.pk_rank_user_id is not None, _op_pk_rank_add),
    (lambda a: a.room_bot_room_id is not None, _op_room_add_bots),
    (lambda a: a.room_online_room_id is not None, _op_room_online),
    (lambda a: _member_lv_mode(a), _op_room_member_lv),
    (lambda a: _anniversary_egg_mode(a), _op_anniversary_egg_smash),
    (lambda a: a.package_gift_user_id is not None, _op_package_gift),
    (lambda a: _family_fund_tier_mode(a), _op_family_fund_tier),
    (lambda a: _family_fund_clear_mode(a), _op_family_fund_clear),
    (lambda a: _family_member_fund_contrib_mode(a), _op_family_member_fund_contrib),
    (lambda a: _family_fund_contrib_mode(a), _op_family_fund_contrib),
    (lambda a: _family_decrease_mode(a), _op_family_decrease_exp),
    (lambda a: _family_query_members_mode(a), _op_family_query_members),
    (lambda a: _family_query_create_time_mode(a), _op_family_query_create_time),
    (lambda a: _family_query_joined_mode(a), _op_family_query_joined),
    (lambda a: _family_delete_mode(a), _op_family_delete),
    (lambda a: a.family_leave_user_id is not None, _op_family_leave),
    (lambda a: a.follow_uid is not None or a.follow_remote_uid is not None, _op_user_follow),
    (lambda a: _family_add_mode(a), _op_family_exp),
    (lambda a: a.noble_user_id is not None, _op_noble),
    (lambda a: a.vip_user_id is not None, _op_vip),
]


def load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.payload_file:
        with open(args.payload_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
    elif args.payload:
        payload = json.loads(args.payload)
    else:
        raise ValueError("必须提供 --payload-file 或 --payload")

    if not isinstance(payload, dict):
        raise ValueError("payload 必须是 JSON object")

    # 模板内 _registry 仅用于 sync_registry 入库，不发给 MOA
    payload.pop("_registry", None)

    apply_top_level_overrides(payload, args)

    for predicate, handler in OPERATIONS:
        if predicate(args):
            handler(args, payload)
            return payload

    _apply_room_expr(payload, args)
    return payload
