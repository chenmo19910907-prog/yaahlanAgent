"""MOA payload 参数构造。"""

from __future__ import annotations

import json
import random
import time
from typing import Any

from .config import section_defaults

CUSTOM_GIFT_RANK_PERIODS = frozenset({"NOW", "PRE", "PRE_PRE"})


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


def set_family_members_query_params(payload: dict[str, Any], family_id: str) -> None:
    family_id = str(family_id).strip()
    if not family_id:
        raise ValueError("family_id 不能为空")
    payload["params"] = [string_param(family_id)]


def set_family_create_time_query_params(payload: dict[str, Any], family_id: str) -> None:
    family_id = str(family_id).strip()
    if not family_id:
        raise ValueError("family_id 不能为空")
    payload["params"] = [string_param(family_id)]


def set_user_joined_family_query_params(payload: dict[str, Any], user_id: str) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    payload["params"] = [string_param(user_id)]


def set_family_leave_params(payload: dict[str, Any], user_id: str) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    body = {"userId": user_id}
    payload["header"] = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    settings = payload.setdefault("settings", {})
    if isinstance(settings, dict):
        settings["headerType"] = "KV"
    payload["params"] = [
        {
            "name": 0,
            "title": "",
            "txt": '{""}',
            "json": json.dumps(body, ensure_ascii=False, separators=(",", ":")),
            "type": "json",
            "value": body,
        }
    ]


def set_family_kick_member_params(
    payload: dict[str, Any],
    *,
    family_id: str,
    operator_id: str,
    remote_id: str,
) -> None:
    family_id = str(family_id).strip()
    operator_id = str(operator_id).strip()
    remote_id = str(remote_id).strip()
    if not family_id:
        raise ValueError("family_id 不能为空")
    if not operator_id:
        raise ValueError("operator_id 不能为空")
    if not remote_id:
        raise ValueError("remote_id 不能为空")
    body = {"familyId": family_id, "userId": operator_id, "remoteId": remote_id}
    header = {"userId": operator_id}
    payload["header"] = json.dumps(header, ensure_ascii=False, separators=(",", ":"))
    settings = payload.setdefault("settings", {})
    if isinstance(settings, dict):
        settings["headerType"] = "KV"
    payload["params"] = [
        {
            "name": 0,
            "title": "",
            "txt": "",
            "json": json.dumps(body, ensure_ascii=False, separators=(",", ":")),
            "type": "json",
            "value": body,
        }
    ]


def set_family_pk_member_list_params(
    payload: dict[str, Any],
    *,
    user_id: str,
    family_id: str,
    date: str,
    offset: int = 0,
    limit: int = 20,
    area: str = "MENA",
) -> None:
    user_id = str(user_id).strip()
    family_id = str(family_id).strip()
    date = str(date).strip()
    area = str(area or "MENA").strip().upper()
    if not user_id:
        raise ValueError("user_id 不能为空")
    if not family_id:
        raise ValueError("family_id 不能为空")
    if not date:
        raise ValueError("date 不能为空")

    body: dict[str, Any] = {}
    params = payload.get("params")
    if isinstance(params, list) and params:
        first = params[0]
        if isinstance(first, dict) and isinstance(first.get("value"), dict):
            body = dict(first["value"])
    if not body:
        raise ValueError("家族PK-成员贡献列表 payload 缺少 params[0].value")

    body["userId"] = user_id
    body["uid"] = user_id
    body["_uid_"] = user_id
    body["familyId"] = family_id
    body["date"] = date
    body["offset"] = int(offset)
    body["limit"] = int(limit)
    body["area"] = area
    header_s = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    payload["header"] = header_s
    settings = payload.setdefault("settings", {})
    if isinstance(settings, dict):
        settings["headerType"] = "TXT"
    payload["params"] = [
        {
            "name": 0,
            "title": 0,
            "txt": "",
            "json": header_s,
            "type": "json",
            "value": body,
        }
    ]


def set_gift_panel_backpack_params(
    payload: dict[str, Any],
    *,
    user_id: str,
    room_id: str | None = None,
    area: str = "MENA",
    clear_hash: bool = False,
    service_url: str | None = None,
) -> None:
    user_id = str(user_id).strip()
    area = str(area or "MENA").strip().upper()
    if not user_id:
        raise ValueError("user_id 不能为空")

    body: dict[str, Any] = {}
    params = payload.get("params")
    if isinstance(params, list) and params:
        first = params[0]
        if isinstance(first, dict) and isinstance(first.get("value"), dict):
            body = dict(first["value"])
    if not body:
        raise ValueError("礼物面板背包 payload 缺少 params[0].value")

    body["userId"] = user_id
    body["uid"] = user_id
    body["area"] = area
    if room_id:
        body["roomId"] = str(room_id).strip()
    if clear_hash:
        body.pop("giftListHash", None)

    header_s = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    payload["header"] = header_s
    if service_url:
        payload["url"] = str(service_url).strip()
    settings = payload.setdefault("settings", {})
    if isinstance(settings, dict):
        settings["headerType"] = "TXT"
    payload["params"] = [
        {
            "name": 0,
            "title": 0,
            "txt": "",
            "json": header_s,
            "type": "json",
            "value": body,
        }
    ]


def set_family_pk_page_params(
    payload: dict[str, Any],
    *,
    user_id: str,
    date: str,
    area: str = "MENA",
) -> None:
    user_id = str(user_id).strip()
    date = str(date).strip()
    area = str(area or "MENA").strip().upper()
    if not user_id:
        raise ValueError("user_id 不能为空")
    if not date:
        raise ValueError("date 不能为空")

    body: dict[str, Any] = {}
    params = payload.get("params")
    if isinstance(params, list) and params:
        first = params[0]
        if isinstance(first, dict) and isinstance(first.get("value"), dict):
            body = dict(first["value"])
    if not body:
        raise ValueError("家族PK-请求页面 payload 缺少 params[0].value")

    body["userId"] = user_id
    body["uid"] = user_id
    body["_uid_"] = user_id
    body["date"] = date
    body["area"] = area
    header_s = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    payload["header"] = header_s
    settings = payload.setdefault("settings", {})
    if isinstance(settings, dict):
        settings["headerType"] = "TXT"
    payload["params"] = [
        {
            "name": 0,
            "title": 0,
            "txt": "",
            "json": header_s,
            "type": "json",
            "value": body,
        }
    ]


def set_family_delete_params(payload: dict[str, Any], family_id: str, owner_user_id: str) -> None:
    family_id = str(family_id).strip()
    owner_user_id = str(owner_user_id).strip()
    if not family_id:
        raise ValueError("family_id 不能为空")
    if not owner_user_id:
        raise ValueError("owner_user_id 不能为空")
    body = {"familyId": family_id, "userId": owner_user_id}
    header = {"userId": owner_user_id}
    payload["header"] = json.dumps(header, ensure_ascii=False, separators=(",", ":"))
    settings = payload.setdefault("settings", {})
    if isinstance(settings, dict):
        settings["headerType"] = "KV"
    payload["params"] = [
        {
            "name": 0,
            "title": "",
            "txt": "",
            "json": json.dumps(body, ensure_ascii=False, separators=(",", ":")),
            "type": "json",
            "value": body,
        }
    ]


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


def set_vip_try_dispatch_params(
    payload: dict[str, Any],
    user_id: str,
    try_level: int,
    duration_seconds: int,
) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    if try_level < 1 or try_level > 10:
        raise ValueError("vip_try_level 必须在 1-10 之间")
    if duration_seconds < 1:
        raise ValueError("vip_try_duration_seconds 必须为正整数")
    payload["method"] = "dispatchTryVip"
    payload["params"] = three_params(user_id, try_level, duration_seconds)


def set_room_downgrade_level_params(payload: dict[str, Any], room_id: str, level: int) -> None:
    room_id = str(room_id).strip()
    if not room_id:
        raise ValueError("room_id 不能为空")
    if level < 1:
        raise ValueError("room_set_level 必须为正整数")
    payload["url"] = "/service/room/internal/room-test-stage"
    payload["method"] = "downgradeRoomLevelForTest"
    payload["params"] = two_params(room_id, level, second_type="int")


def set_custom_gift_reset_expire_params(payload: dict[str, Any], user_id: str) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    payload["url"] = "/service/voga-components/gateway/custom-gift-stage"
    payload["method"] = "resetExpireTime"
    payload["params"] = [string_param(user_id)]


def custom_gift_rank_defaults() -> dict[str, Any]:
    return section_defaults(
        "custom_gift_rank",
        {
            "defaultUserId": "100493343",
            "defaultPeriod": "PRE",
            "defaultArea": "MENA",
            "headerTemplate": {},
        },
    )


def _indexed_param(name: int, value: Any, *, ptype: str, json_str: str = "") -> dict[str, Any]:
    display = str(value)
    return {
        "title": "",
        "name": name,
        "txt": display,
        "json": json_str,
        "type": ptype,
        "value": display if ptype in ("long", "int") else value,
    }


def build_custom_gift_rank_header(*, user_id: str, area: str) -> str:
    user_id = str(user_id).strip()
    area = str(area).strip().upper()
    if not user_id:
        raise ValueError("user_id 不能为空")
    if not area:
        raise ValueError("area 不能为空")

    defaults = custom_gift_rank_defaults()
    template = defaults.get("headerTemplate")
    if not isinstance(template, dict):
        template = {}

    header = dict(template)
    header["localTime"] = int(time.time() * 1000)
    header["uid"] = user_id
    header["userId"] = user_id
    header["area"] = area
    if "mmuid" not in header and "deviceId" in header:
        header["mmuid"] = header["deviceId"]
    return json.dumps(header, ensure_ascii=False, separators=(",", ": "))


def set_custom_gift_rank_active_params(
    payload: dict[str, Any],
    *,
    period: str,
    area: str,
    gift_id: str,
    active_value: int,
    user_id: str,
) -> None:
    period = str(period).strip().upper()
    area = str(area).strip().upper()
    gift_id = str(gift_id).strip()
    user_id = str(user_id).strip()

    if period not in CUSTOM_GIFT_RANK_PERIODS:
        raise ValueError(f"period 必须是 {sorted(CUSTOM_GIFT_RANK_PERIODS)} 之一")
    if not area:
        raise ValueError("area 不能为空")
    if not gift_id:
        raise ValueError("gift_id 不能为空")
    if active_value <= 0:
        raise ValueError("active_value 必须为正整数")
    if not user_id:
        raise ValueError("user_id 不能为空")

    header_str = build_custom_gift_rank_header(user_id=user_id, area=area)
    payload["url"] = "/service/room/internal/room-rank-list-stage"
    payload["method"] = "mockCustomGiftRankData"
    payload["header"] = header_str
    payload["params"] = [
        _indexed_param(0, period, ptype="string", json_str=header_str),
        _indexed_param(1, area, ptype="string"),
        _indexed_param(2, gift_id, ptype="string"),
        _indexed_param(3, active_value, ptype="long"),
    ]


def set_custom_gift_rank_delete_params(
    payload: dict[str, Any],
    *,
    area: str,
    gift_id: str,
) -> None:
    area = str(area).strip().upper()
    gift_id = str(gift_id).strip()
    if not area:
        raise ValueError("area 不能为空")
    if not gift_id:
        raise ValueError("gift_id 不能为空")

    payload["url"] = "/service/room/internal/room-rank-list-stage"
    payload["method"] = "delCustomGiftRankData"
    payload["header"] = ""
    payload["params"] = [
        _indexed_param(0, area, ptype="string"),
        _indexed_param(1, gift_id, ptype="string"),
    ]


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


def set_id_auth_del_relation_by_scene_params(
    payload: dict[str, Any],
    user_id: str,
    scene: str,
) -> None:
    user_id = str(user_id).strip()
    scene = str(scene).strip().upper()
    if not user_id:
        raise ValueError("user_id 不能为空")
    if scene not in ("DEALER", "ANCHOR"):
        raise ValueError("scene 须为 DEALER（币商）或 ANCHOR（普通/主播）")
    payload["params"] = two_params(user_id, scene, second_type="string")


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


def build_package_gift_request_value(
    user_id: str,
    *,
    give_user_id: str = "",
    base_product_id: str | None = None,
    product_num: int | None = None,
    out_order_id: str | None = None,
) -> dict[str, Any]:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")

    defaults = package_gift_defaults()
    gift_details: list[dict[str, Any]] = []

    if base_product_id is not None and str(base_product_id).strip():
        num = product_num if product_num is not None else 1
        try:
            num_int = int(num)
        except (TypeError, ValueError) as e:
            raise ValueError(f"gift productNum 无效: {num}") from e
        if num_int <= 0:
            raise ValueError("gift productNum 必须为正整数")
        gift_details.append({"baseProductId": str(base_product_id).strip(), "productNum": num_int})
    else:
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

    return {
        "userId": user_id,
        "giveUserId": str(give_user_id or "").strip(),
        "outOrderId": out_order_id
        or random_package_gift_out_order_id(
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


def set_package_gift_params(
    payload: dict[str, Any],
    user_id: str,
    *,
    product_num: int | None = None,
    give_user_id: str = "",
    base_product_id: str | None = None,
) -> None:
    value = build_package_gift_request_value(
        user_id,
        give_user_id=give_user_id,
        base_product_id=base_product_id,
        product_num=product_num,
    )
    payload["params"] = [json_param(value)]


ANNIVERSARY_EGG_DEFAULT_BATCH = 10


def resolve_anniversary_egg_batch_count(
    *,
    remaining: int | None = None,
    explicit_count: int | None = None,
) -> int:
    """默认一次砸蛋数量：剩余 >10 → 10；剩余 ≤10 → 剩余次数。

    显式传入 explicit_count 时按其值。
    未传剩余次数时，默认按一次砸 10 个（仅日志期望值；实际次数以返回值/剩余差值为准）。
    """
    if explicit_count is not None:
        count = int(explicit_count)
        if count <= 0:
            raise ValueError("anniversary_egg smashCount 须为正整数")
        return count
    if remaining is not None:
        left = int(remaining)
        if left <= 0:
            raise ValueError("剩余砸蛋次数为 0，无法砸蛋")
        return min(ANNIVERSARY_EGG_DEFAULT_BATCH, left)
    return ANNIVERSARY_EGG_DEFAULT_BATCH


def anniversary_egg_batch_calls_for_target(target_eggs: int) -> int:
    """按目标砸蛋总数估算需调用 smashEgg 的次数（每次最多 DEFAULT_BATCH）。"""
    target = int(target_eggs)
    if target <= 0:
        raise ValueError("anniversary_egg smashCount 须为正整数")
    return (target + ANNIVERSARY_EGG_DEFAULT_BATCH - 1) // ANNIVERSARY_EGG_DEFAULT_BATCH


def set_anniversary_egg_smash_params(
    payload: dict[str, Any],
    *,
    user_id: str,
    room_id: str,
    smash_count: int | None = None,
    remaining: int | None = None,
    lang: str = "en",
) -> None:
    """year3GiftService.smashEgg(userId, roomId, lang)。

    房间应传用户自己的房间；本次砸蛋次数以接口返回 / 剩余次数差值为准。
    """
    user_id = str(user_id).strip()
    room_id = str(room_id).strip()
    lang = str(lang or "en").strip() or "en"
    if not user_id:
        raise ValueError("anniversary_egg userId 不能为空")
    if not room_id:
        raise ValueError("anniversary_egg roomId 不能为空（默认取 Admin 自己的房间）")
    batch = resolve_anniversary_egg_batch_count(
        remaining=remaining,
        explicit_count=smash_count,
    )
    expr = (
        f'return context.getBean("year3GiftService")'
        f'.smashEgg("{user_id}","{room_id}","{lang}");'
    )
    payload["url"] = "/service/voga-mts-vas-backdoor"
    payload["method"] = "execute"
    payload["params"] = [string_param(expr)]
    payload["_anniversaryEggBatch"] = batch


def set_room_online_params(payload: dict[str, Any], room_id: str, entry_limit: int, auto_mic: int) -> None:
    room_id = str(room_id).strip()
    if not room_id:
        raise ValueError("room_id 不能为空")
    if entry_limit < 0:
        raise ValueError("entry_limit 不能为负数")
    if auto_mic < 0:
        raise ValueError("auto_mic 不能为负数")
    payload["params"] = [
        _param("参数1", "1", room_id, ptype="string", txt=room_id),
        _param("参数2", "2", str(entry_limit), ptype="int", txt=str(entry_limit)),
        _param("参数3", "3", str(auto_mic), ptype="int", txt=str(auto_mic)),
        _param("参数4", "4", "", ptype="string", txt=""),
    ]


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


def normalize_cp_pair_key(uid_a: str, uid_b: str) -> str:
    a = int(str(uid_a).strip())
    b = int(str(uid_b).strip())
    small, large = (a, b) if a < b else (b, a)
    return f"{small}-{large}"


def parse_cp_pair_keys(raw: str) -> list[str]:
    text = str(raw).strip()
    if not text:
        raise ValueError("cp-pairs 不能为空")
    keys: list[str] = []
    for part in text.split(","):
        key = part.strip()
        if not key:
            continue
        if "-" not in key:
            raise ValueError(f"CP 对格式错误（应为小uid-大uid）: {key}")
        left, right = key.split("-", 1)
        keys.append(normalize_cp_pair_key(left, right))
    if not keys:
        raise ValueError("cp-pairs 不能为空")
    return keys


def set_cp_ferris_wheel_tier_params(payload: dict[str, Any], tier: int, pair_keys: list[str]) -> None:
    if tier < 1 or tier > 5:
        raise ValueError("cp-ferris-tier 必须在 1–5 之间（1=D、2=C、3=B、4=A、5=S）")
    if not pair_keys:
        raise ValueError("cp-pairs 不能为空")
    cp_json = json.dumps(pair_keys, ensure_ascii=False, separators=(",", ":"))
    payload["params"] = [
        _param("参数1", "1", str(tier), ptype="string", txt=str(tier)),
        _param("参数2", "2", pair_keys, ptype="json", txt=pair_keys, json_str=cp_json),
    ]


def set_cp_ferris_wheel_area_params(payload: dict[str, Any], area: str) -> None:
    area_code = str(area).strip().upper()
    if not area_code:
        raise ValueError("cp-ferris-area 不能为空")
    payload["params"] = [_param("参数1", "1", area_code, ptype="string", txt=area_code)]


def user_prop_query_defaults() -> dict[str, Any]:
    return section_defaults("user_prop_query", {"appId": 2005, "lang": "en"})


def set_user_prop_query_params(
    payload: dict[str, Any],
    *,
    user_id: str,
    prop_type_code: str,
    lang: str | None = None,
    app_id: int | None = None,
) -> None:
    user_id = str(user_id).strip()
    prop_type_code = str(prop_type_code).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    if not prop_type_code:
        raise ValueError("prop_type_code 不能为空")
    defaults = user_prop_query_defaults()
    value = {
        "appId": int(app_id if app_id is not None else defaults.get("appId", 2005)),
        "userId": user_id,
        "propTypeCode": prop_type_code,
        "lang": str(lang or defaults.get("lang", "en")),
    }
    payload["params"] = [json_param(value)]


def set_user_follow_params(
    payload: dict[str, Any],
    uid: str,
    remote_uid: str,
    *,
    relation_type: int = 1,
) -> None:
    uid = str(uid).strip()
    remote_uid = str(remote_uid).strip()
    if not uid:
        raise ValueError("uid 不能为空")
    if not remote_uid:
        raise ValueError("remoteUid 不能为空")
    if relation_type != 1:
        raise ValueError("relationType 目前仅支持 1（关注）")
    body = {"uid": uid, "remoteUid": remote_uid, "relationType": relation_type}
    payload["url"] = "/service/voga-mts-user-relation-stage"
    payload["method"] = "addUserRelation"
    payload["params"] = [
        json_param(body),
        _param("参数2", "2", "", ptype="string", txt=""),
    ]
