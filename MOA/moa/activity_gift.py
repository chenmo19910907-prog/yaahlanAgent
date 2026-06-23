"""活动模拟送礼 MOA（vas/gift-call-back 回调造数）。"""

from __future__ import annotations

import json
import random
import time
from typing import Any

from .config import section_defaults
from .params import _param


def activity_mock_gift_defaults() -> dict[str, Any]:
    return section_defaults(
        "activity_mock_gift",
        {
            "appId": 2005,
            "flag": "test",
            "orderStatus": 20,
            "channel": 2,
            "groupId": 2005000187,
            "businessId": 2005000186,
            "category": 2005000189,
            "productId": 2005000200,
            "productType": "0_0",
            "productNum": 1,
            "price": 2000,
            "totalFee": 1,
            "realFee": 1,
            "paySource": 0,
            "extraSource": "p2p",
            "extraRole": "user",
            "giftNum": 1,
            "timeZone": "Asia/Shanghai",
            "methods": {},
        },
    )


def resolve_activity_gift_fields(
    *,
    method: str | None,
    product_id: str | int | None,
    price: int | None,
    real_fee: int | None,
    total_fee: int | None,
) -> tuple[int, int, int, int]:
    """优先级：CLI 参数 > thresholds.methods[method] > activity_mock_gift 全局默认。"""
    defaults = activity_mock_gift_defaults()
    method_cfg: dict[str, Any] = {}
    if method:
        methods = defaults.get("methods")
        if isinstance(methods, dict):
            raw = methods.get(method)
            if isinstance(raw, dict):
                method_cfg = raw

    def _pick_int(
        cli_value: str | int | None,
        cfg_key: str,
        default_key: str,
        *,
        label: str,
    ) -> int:
        if cli_value is not None and str(cli_value).strip() != "":
            try:
                return int(cli_value)
            except (TypeError, ValueError) as e:
                raise ValueError(f"{label} 无效: {cli_value}") from e
        if cfg_key in method_cfg and method_cfg[cfg_key] is not None:
            try:
                return int(method_cfg[cfg_key])
            except (TypeError, ValueError) as e:
                raise ValueError(f"methods.{method}.{cfg_key} 无效: {method_cfg[cfg_key]}") from e
        try:
            return int(defaults[default_key])
        except (TypeError, ValueError, KeyError) as e:
            raise ValueError(
                f"缺少 {label}：请传 CLI 参数，或在 thresholds.json activity_mock_gift.methods 配置"
            ) from e

    resolved_product_id = _pick_int(product_id, "productId", "productId", label="product_id")
    resolved_price = _pick_int(price, "price", "price", label="price")
    resolved_real_fee = _pick_int(real_fee, "realFee", "realFee", label="real_fee")
    resolved_total_fee = _pick_int(total_fee, "totalFee", "totalFee", label="total_fee")
    # 未单独配置时，计值字段与 price 对齐（榜单通常看 real_fee，不是展示价 price）
    if real_fee is None and "realFee" not in method_cfg:
        resolved_real_fee = resolved_price
    if total_fee is None and "totalFee" not in method_cfg:
        resolved_total_fee = resolved_price
    return resolved_product_id, resolved_price, resolved_real_fee, resolved_total_fee


def random_activity_order_id() -> str:
    millis = int(time.time() * 1000)
    suffix = random.randint(10**14, 10**15 - 1)
    return f"{millis}{suffix}"


def build_activity_gift_extra(from_user_id: str, to_user_id: str, *, defaults: dict[str, Any]) -> str:
    local_ms = int(time.time() * 1000)
    extra_obj = {
        "timeZone": defaults.get("timeZone", "Asia/Shanghai"),
        "localTime": str(local_ms),
        "source": defaults.get("extraSource", "p2p"),
        "role": defaults.get("extraRole", "user"),
        "receiveUser": {
            "receiveUserId": str(to_user_id),
            "extra": None,
            "shareRoleList": [
                {
                    "shareUserId": str(from_user_id),
                    "roleId": 0,
                    "settleType": 0,
                    "guildId": None,
                }
            ],
        },
        "giftNum": int(defaults.get("giftNum", 1)),
    }
    return json.dumps(extra_obj, ensure_ascii=False, separators=(",", ":"))


def build_activity_gift_order_body(
    from_user_id: str,
    to_user_id: str,
    *,
    method: str | None = None,
    product_id: str | int | None = None,
    product_num: int | None = None,
    price: int | None = None,
    real_fee: int | None = None,
    total_fee: int | None = None,
    room_id: str = "",
) -> dict[str, Any]:
    from_user_id = str(from_user_id).strip()
    to_user_id = str(to_user_id).strip()
    if not from_user_id:
        raise ValueError("from_user_id 不能为空")
    if not to_user_id:
        raise ValueError("to_user_id 不能为空")

    defaults = activity_mock_gift_defaults()
    now_ms = int(time.time() * 1000)
    resolved_product_id, resolved_price, resolved_real_fee, resolved_total_fee = resolve_activity_gift_fields(
        method=method,
        product_id=product_id,
        price=price,
        real_fee=real_fee,
        total_fee=total_fee,
    )

    return {
        "app_id": int(defaults["appId"]),
        "userid": from_user_id,
        "order_id": random_activity_order_id(),
        "out_order_id": random_activity_order_id(),
        "order_status": int(defaults["orderStatus"]),
        "create_time": now_ms,
        "update_time": now_ms,
        "receive_userid": to_user_id,
        "pay_order_id": random_activity_order_id(),
        "channel": int(defaults["channel"]),
        "group_id": int(defaults["groupId"]),
        "business_id": int(defaults["businessId"]),
        "category": int(defaults["category"]),
        "product_id": resolved_product_id,
        "product_type": str(defaults["productType"]),
        "product_num": int(product_num if product_num is not None else defaults["productNum"]),
        "price": resolved_price,
        "total_fee": resolved_total_fee,
        "real_fee": resolved_real_fee,
        "pay_source": int(defaults["paySource"]),
        "room_id": room_id,
        "pay_time": now_ms,
        "confirm_time": now_ms,
        "extra": build_activity_gift_extra(from_user_id, to_user_id, defaults=defaults),
    }


def set_activity_mock_gift_params(
    payload: dict[str, Any],
    from_user_id: str,
    to_user_id: str,
    *,
    flag: str | None = None,
    method: str | None = None,
    product_id: str | int | None = None,
    product_num: int | None = None,
    price: int | None = None,
    real_fee: int | None = None,
    total_fee: int | None = None,
    room_id: str = "",
) -> None:
    defaults = activity_mock_gift_defaults()
    flag_value = str(flag if flag is not None else defaults.get("flag", "test"))

    payload.setdefault("url", "/service/vas/gift-call-back")
    if method:
        payload["method"] = method

    order_json = json.dumps(
        build_activity_gift_order_body(
            from_user_id,
            to_user_id,
            method=method,
            product_id=product_id,
            product_num=product_num,
            price=price,
            real_fee=real_fee,
            total_fee=total_fee,
            room_id=room_id,
        ),
        ensure_ascii=False,
        separators=(",", ":"),
    )

    payload["params"] = [
        _param("参数1", "1", flag_value, ptype="string", txt=flag_value),
        _param("参数2", "2", order_json, ptype="string", txt=order_json),
    ]
