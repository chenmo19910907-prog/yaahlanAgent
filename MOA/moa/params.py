"""MOA payload 参数构造。"""

from __future__ import annotations

import json
import random
from typing import Any

from .config import section_defaults


def _param(title: str, name: str, value: Any, *, ptype: str, txt: Any | None = None, json_str: str = "") -> dict[str, Any]:
    display = txt if txt is not None else value
    return {
        "title": title,
        "name": name,
        "txt": display,
        "json": json_str,
        "type": ptype,
        "value": str(value) if ptype in ("long", "int") else value,
    }


def string_param(value: str) -> dict[str, Any]:
    return _param("参数1", "1", value, ptype="string", txt=value)


def json_param(value: dict[str, Any]) -> dict[str, Any]:
    return _param(
        "参数1",
        "1",
        value,
        ptype="json",
        txt=value,
        json_str=json.dumps(value, ensure_ascii=False, separators=(",", ":")),
    )


def json_array_param(values: list[Any]) -> dict[str, Any]:
    return _param(
        "参数1",
        "1",
        values,
        ptype="json",
        txt=values,
        json_str=json.dumps(values, ensure_ascii=False, separators=(",", ":")),
    )


def two_params(first: str, second: int | str, *, second_type: str = "long") -> list[dict[str, Any]]:
    second_str = str(second)
    return [
        _param("参数1", "1", first, ptype="string", txt=first),
        _param("参数2", "2", second_str, ptype=second_type, txt=second_str),
    ]


def three_params(room_id: str, second: int, third: int, *, second_type: str = "int", third_type: str = "int") -> list[dict[str, Any]]:
    return [
        _param("参数1", "1", room_id, ptype="string", txt=room_id),
        _param("参数2", "2", str(second), ptype=second_type, txt=str(second)),
        _param("参数3", "3", str(third), ptype=third_type, txt=str(third)),
    ]


def random_five_digit_out_order_id(prefix: str = "system") -> str:
    return f"{prefix}-{random.randint(10000, 99999)}"


def random_thirteen_digit() -> int:
    return random.randint(10**12, 10**13 - 1)


def random_package_gift_out_order_id(prefix: str, middle: str) -> str:
    return f"{prefix}-{middle}-{random_thirteen_digit()}"


def set_vip_params(payload: dict[str, Any], user_id: str, vip_exp_delta: int) -> None:
    if vip_exp_delta < 0:
        raise ValueError("vip_exp_delta 不能为负数")
    payload["params"] = two_params(str(user_id), vip_exp_delta, second_type="int")


def set_vip_info_query_params(payload: dict[str, Any], user_id: str) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    payload["method"] = "getVipInfo"
    payload["params"] = [string_param(user_id)]


def set_noble_params(payload: dict[str, Any], user_id: str, noble_exp_delta: int) -> None:
    if noble_exp_delta < 0:
        raise ValueError("noble_exp_delta 不能为负数")
    payload["params"] = two_params(str(user_id), noble_exp_delta, second_type="long")


def set_family_exp_params(payload: dict[str, Any], family_id: str, exp_delta: int) -> None:
    family_id = str(family_id).strip()
    if not family_id:
        raise ValueError("family_id 不能为空")
    if exp_delta < 0:
        raise ValueError("exp_delta 不能为负数")
    payload["params"] = two_params(family_id, exp_delta, second_type="long")


def set_family_decrease_exp_params(payload: dict[str, Any], family_id: str, decrease_exp: int) -> None:
    family_id = str(family_id).strip()
    if not family_id:
        raise ValueError("family_id 不能为空")
    if decrease_exp <= 0:
        raise ValueError("decrease_exp 必须为正整数（脚本会自动传负值）")
    payload["params"] = two_params(family_id, -decrease_exp, second_type="long")


FAMILY_FUND_TIERS = frozenset({"A", "B", "C"})
FAMILY_MEMBER_FUND_API_SCALE = 2


def family_member_fund_api_value(contrib: int) -> str:
    if contrib <= 0:
        raise ValueError("family_member_fund_contrib 必须为正整数")
    return str(contrib * FAMILY_MEMBER_FUND_API_SCALE)


def set_family_member_fund_contrib_params(
    payload: dict[str, Any],
    family_id: str,
    week_key: str,
    user_contributions: dict[str, int],
) -> None:
    family_id = str(family_id).strip()
    if not family_id:
        raise ValueError("family_id 不能为空")
    week_key = str(week_key).strip()
    if not week_key.endswith("-week"):
        raise ValueError(f"week_key 格式无效: {week_key}，应为 YYYYMMDD-week")
    if not user_contributions:
        raise ValueError("user_contributions 不能为空")
    api_map = {
        str(user_id).strip(): family_member_fund_api_value(contrib)
        for user_id, contrib in user_contributions.items()
        if str(user_id).strip()
    }
    if not api_map:
        raise ValueError("user_contributions 不能为空")
    payload["params"] = [
        _param("参数1", "1", family_id, ptype="string", txt=family_id),
        _param("参数2", "2", week_key, ptype="string", txt=week_key),
        _param(
            "参数3",
            "3",
            api_map,
            ptype="json",
            txt=api_map,
            json_str=json.dumps(api_map, ensure_ascii=False, separators=(",", ":")),
        ),
    ]


def set_family_fund_tier_params(
    payload: dict[str, Any],
    family_ids: str | list[str],
    tier: str,
    *,
    flag: int = 0,
) -> None:
    if isinstance(family_ids, str):
        ids = [item.strip() for item in family_ids.split(",") if item.strip()]
    else:
        ids = [str(item).strip() for item in family_ids if str(item).strip()]
    if not ids:
        raise ValueError("family_ids 不能为空")
    tier = str(tier).strip().upper()
    if tier not in FAMILY_FUND_TIERS:
        raise ValueError(f"family_fund_tier 无效: {tier}，支持: {sorted(FAMILY_FUND_TIERS)}")
    payload["params"] = [
        json_array_param(ids),
        _param("参数2", "2", tier, ptype="string", txt=tier),
        _param("参数3", "3", str(flag), ptype="int", txt=str(flag)),
    ]


def set_backdoor_execute_expr(payload: dict[str, Any], expr: str) -> None:
    expr = str(expr).strip()
    if not expr:
        raise ValueError("backdoor expr 不能为空")
    payload["params"] = [string_param(expr)]


def set_vip_del_params(payload: dict[str, Any], user_id: str) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    payload["params"] = [string_param(user_id)]


def set_id_auth_params(payload: dict[str, Any], user_id: str) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    payload["params"] = [json_param({"userId": user_id})]


def set_id_auth_reset_expire_params(payload: dict[str, Any], user_id: str, expire_ms: int) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    if expire_ms <= 0:
        raise ValueError("expire_ms 必须为正整数（毫秒时间戳）")
    payload["params"] = two_params(user_id, expire_ms)


def set_id_auth_delete_person_params(payload: dict[str, Any], user_id: str) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    payload["params"] = [string_param(user_id)]


def diamond_provide_defaults() -> dict[str, str]:
    return section_defaults(
        "diamond_provide",
        {
            "activityId": "2005000496",
            "taskId": "2005000497",
            "signKey": "189ad0ec4e41438abf29e2f2874d94eb",
            "outOrderIdPrefix": "system",
        },
    )


def query_login_status_defaults() -> dict[str, Any]:
    return section_defaults(
        "query_login_status",
        {
            "appId": 2005,
            "loginType": "MOBILE",
            "areaCode": "86",
        },
    )


def set_query_login_status_params(
    payload: dict[str, Any],
    *,
    area_code: str,
    mobile: str,
    app_id: int | None = None,
    login_type: str | None = None,
) -> None:
    area_code = str(area_code).strip().lstrip("+")
    mobile = str(mobile).strip()
    if not area_code:
        raise ValueError("area_code 不能为空")
    if not mobile:
        raise ValueError("mobile 不能为空")

    defaults = query_login_status_defaults()
    value = {
        "loginType": login_type or str(defaults["loginType"]),
        "areaCode": area_code,
        "thirdUid": mobile,
        "appId": int(app_id if app_id is not None else defaults["appId"]),
    }
    payload["params"] = [json_param(value)]


def set_change_user_area_params(payload: dict[str, Any], user_id: str, area_code: str) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    area_code = str(area_code).strip().upper()
    if not area_code:
        raise ValueError("area_code 不能为空")
    payload["params"] = two_params(user_id, area_code, second_type="string")


def set_diamond_query_params(payload: dict[str, Any], user_id: str) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    payload["params"] = [string_param(user_id)]


def set_diamond_provide_params(payload: dict[str, Any], user_id: str, num: int) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    if num <= 0:
        raise ValueError("num 必须为正整数（钻石数量）")

    defaults = diamond_provide_defaults()
    value = {
        "userId": user_id,
        "num": num,
        "activityId": defaults["activityId"],
        "taskId": defaults["taskId"],
        "outOrderId": random_five_digit_out_order_id(defaults["outOrderIdPrefix"]),
        "signKey": defaults["signKey"],
    }
    payload["params"] = [json_param(value)]


def package_gift_defaults() -> dict[str, Any]:
    default_gifts = [
        {"baseProductId": "2005001272", "productNum": 100},
        {"baseProductId": "2005001282", "productNum": 100},
    ]
    return section_defaults(
        "package_gift",
        {
            "outOrderIdPrefix": "PACKAGE_GIFT",
            "outOrderIdMiddle": "100328136",
            "category": "2005000189",
            "source": 2005001287,
            "signKey": "76b26f6deb1e4851b728e3b0770629db",
            "realFee": "0",
            "expireSeconds": 86339,
            "giftDetails": default_gifts,
        },
    )


def set_package_gift_params(
    payload: dict[str, Any],
    user_id: str,
    *,
    product_num: int | None = None,
    give_user_id: str = "",
) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")

    defaults = package_gift_defaults()
    gift_details: list[dict[str, Any]] = []
    for item in defaults["giftDetails"]:
        if not isinstance(item, dict) or item.get("baseProductId") is None:
            continue
        num = product_num if product_num is not None else item.get("productNum", 100)
        try:
            num_int = int(num)
        except (TypeError, ValueError) as e:
            raise ValueError(f"gift productNum 无效: {num}") from e
        if num_int <= 0:
            raise ValueError("gift productNum 必须为正整数")
        gift_details.append({"baseProductId": str(item["baseProductId"]), "productNum": num_int})

    if not gift_details:
        raise ValueError("package_gift.giftDetails 配置为空或无效")

    value = {
        "userId": user_id,
        "giveUserId": give_user_id,
        "outOrderId": random_package_gift_out_order_id(
            str(defaults["outOrderIdPrefix"]),
            str(defaults["outOrderIdMiddle"]),
        ),
        "category": str(defaults["category"]),
        "source": int(defaults["source"]),
        "giftDetails": gift_details,
        "realFee": str(defaults["realFee"]),
        "expireSeconds": int(defaults["expireSeconds"]),
        "signKey": str(defaults["signKey"]),
    }
    payload["params"] = [json_param(value)]


def set_room_bot_params(payload: dict[str, Any], room_id: str, total_bots: int, on_mic_bots: int) -> None:
    room_id = str(room_id).strip()
    if not room_id:
        raise ValueError("room_id 不能为空")
    if total_bots <= 0:
        raise ValueError("total_bots 必须为正整数")
    if on_mic_bots < 0:
        raise ValueError("on_mic_bots 不能为负数")
    if on_mic_bots > total_bots:
        raise ValueError("on_mic_bots 不能大于 total_bots")
    payload["params"] = three_params(room_id, total_bots, on_mic_bots)


def set_room_member_lv_params(payload: dict[str, Any], room_id: str, user_id: str, exp_delta: int) -> None:
    room_id = str(room_id).strip()
    user_id = str(user_id).strip()
    if not room_id:
        raise ValueError("room_id 不能为空")
    if not user_id:
        raise ValueError("user_id 不能为空")
    if exp_delta < 0:
        raise ValueError("exp_delta 不能为负数")
    payload["params"] = [
        _param("参数1", "1", room_id, ptype="string", txt=room_id),
        _param("参数2", "2", user_id, ptype="string", txt=user_id),
        _param("参数3", "3", str(exp_delta), ptype="int", txt=str(exp_delta)),
    ]
