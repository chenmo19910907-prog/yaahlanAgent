"""背包礼物下发与背包送礼（addPackageGift + sendMiddlePackageGift）。"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .client import MoaClient, extract_ec_em_result, extract_inner_result, outer_success
from .params import build_package_gift_request_value, package_gift_defaults


_SERVICE_URL = "/service/voga-base-service-middle-gift-stage"

_DELIVERY_NOTE = (
    "MOA addPackageGift 仅下发到送礼方背包；sendMiddlePackageGift 即使 result=true "
    "也不会触发客户端 v2/gift/send，收礼方通常不到账。"
    "真实送礼须 ADB 打开礼物面板从背包送出，并用 Tunnel 验收 gift/send ec=200。"
)


def _base_payload(method: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "moa",
        "key": "momo.pt.toB.cosmos-server.quality-platform.codequality",
        "url": _SERVICE_URL,
        "method": method,
        "header": "",
        "params": [
            {
                "title": "参数1",
                "name": "1",
                "type": "json",
                "txt": value,
                "json": json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                "value": value,
            }
        ],
        "settings": {"time": "2000", "group": "default", "host": "", "headerType": "TXT"},
        "region": "alpha",
        "env": "alpha",
        "cluster": "stage",
        "server": "config",
        "momoId": "df4c6f364f9fcae3",
        "momoName": "e88aa376b29864ad",
    }


def parse_add_package_gift_result(resp: dict[str, Any]) -> dict[str, Any]:
    ec, em, _ = extract_ec_em_result(resp)
    if not outer_success(ec):
        return {"ok": False, "outerEc": ec, "outerEm": em, "orderId": None}
    try:
        inner_ec, inner_em, inner_result = extract_inner_result(resp)
    except RuntimeError as e:
        return {"ok": False, "error": str(e), "orderId": None}
    order_id = None
    if isinstance(inner_result, dict):
        order_id = inner_result.get("orderId")
    return {
        "ok": inner_ec == 0,
        "innerEc": inner_ec,
        "innerEm": inner_em,
        "orderId": order_id,
    }


def parse_send_middle_package_gift_result(resp: dict[str, Any]) -> dict[str, Any]:
    ec, em, _ = extract_ec_em_result(resp)
    if not outer_success(ec):
        return {"ok": False, "outerEc": ec, "outerEm": em, "result": None}
    try:
        inner_ec, inner_em, inner_result = extract_inner_result(resp)
    except RuntimeError as e:
        return {"ok": False, "error": str(e), "result": None}
    sent = inner_result is True or (
        isinstance(inner_result, str) and inner_result.lower() == "true"
    )
    return {
        "ok": inner_ec == 0 and sent,
        "innerEc": inner_ec,
        "innerEm": inner_em,
        "result": inner_result,
    }


def resolve_package_gift_send_ids(args: argparse.Namespace) -> tuple[str, str]:
    from_user_id = str(args.package_gift_user_id or "").strip()
    to_user_id = str(args.package_gift_to_user_id or "").strip()
    add_only = bool(getattr(args, "package_gift_add_only", False))
    if not from_user_id:
        raise ValueError("背包送礼须指定 --package-gift-user-id（送礼方）")
    if add_only:
        return from_user_id, to_user_id
    if not to_user_id:
        raise ValueError("背包送礼须指定 --package-gift-to-user-id（收礼方）")
    if from_user_id == to_user_id:
        raise ValueError("送礼方与收礼方不能相同")
    return from_user_id, to_user_id


def resolve_package_gift_base_id(args: argparse.Namespace) -> str:
    raw = args.package_gift_base_id
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    defaults = package_gift_defaults()
    send_default = defaults.get("sendDefaultBaseProductId")
    if send_default:
        return str(send_default)
    gift_details = defaults.get("giftDetails")
    if isinstance(gift_details, list) and gift_details:
        first = gift_details[0]
        if isinstance(first, dict) and first.get("baseProductId") is not None:
            return str(first["baseProductId"])
    raise ValueError("缺少 --package-gift-base-id，且 config 未配置 sendDefaultBaseProductId")


def run_package_gift_send(args: argparse.Namespace, client: MoaClient) -> int:
    from_user_id, to_user_id = resolve_package_gift_send_ids(args)
    base_product_id = resolve_package_gift_base_id(args)
    product_num = args.package_gift_num if args.package_gift_num is not None else 1
    if product_num <= 0:
        raise ValueError("package-gift-num 必须为正整数")

    add_only = bool(getattr(args, "package_gift_add_only", False))
    accept_moa_send = bool(getattr(args, "package_gift_accept_moa_send", False))

    summary: dict[str, Any] = {
        "fromUserId": from_user_id,
        "toUserId": to_user_id,
        "baseProductId": base_product_id,
        "productNum": product_num,
        "serviceUrl": _SERVICE_URL,
        "deliveryNote": _DELIVERY_NOTE,
        "steps": {},
        "addSucceeded": False,
        "moaSendAccepted": None,
        "delivered": False,
        "success": False,
    }

    if not args.package_gift_skip_add:
        add_value = build_package_gift_request_value(
            from_user_id,
            give_user_id="",
            base_product_id=base_product_id,
            product_num=product_num,
        )
        add_payload = _base_payload("addPackageGift", add_value)
        print(
            f"步骤 1 addPackageGift: userId={from_user_id} baseId={base_product_id} x{product_num}",
            file=sys.stderr,
        )
        add_resp = client.post(add_payload)
        add_step = parse_add_package_gift_result(add_resp)
        add_step["outOrderId"] = add_value.get("outOrderId")
        summary["steps"]["addPackageGift"] = add_step
        summary["addSucceeded"] = bool(add_step.get("ok"))
        if not add_step.get("ok"):
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            print("背包礼物下发失败：addPackageGift 未成功", file=sys.stderr)
            return 3
    else:
        summary["steps"]["addPackageGift"] = {"skipped": True, "ok": True}
        summary["addSucceeded"] = True

    if add_only:
        summary["success"] = summary["addSucceeded"]
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if summary["success"]:
            print(
                "背包礼物已下发到送礼方；真实送礼请用 ADB 从背包面板送出并 Tunnel 验收 gift/send。",
                file=sys.stderr,
            )
            return 0
        return 3

    send_value = build_package_gift_request_value(
        from_user_id,
        give_user_id=to_user_id,
        base_product_id=base_product_id,
        product_num=product_num,
    )
    send_payload = _base_payload("sendMiddlePackageGift", send_value)
    print(
        f"步骤 2 sendMiddlePackageGift: {from_user_id} -> {to_user_id} "
        f"baseId={base_product_id} x{product_num}",
        file=sys.stderr,
    )
    send_resp = client.post(send_payload)
    send_step = parse_send_middle_package_gift_result(send_resp)
    send_step["outOrderId"] = send_value.get("outOrderId")
    summary["steps"]["sendMiddlePackageGift"] = send_step
    moa_send_ok = bool(send_step.get("ok"))
    summary["moaSendAccepted"] = moa_send_ok

    if accept_moa_send:
        summary["success"] = summary["addSucceeded"] and moa_send_ok
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if not summary["success"]:
            print("背包送礼失败：sendMiddlePackageGift 返回 result 非 true", file=sys.stderr)
            return 3
        print(
            "警告：已按 --package-gift-accept-moa-send 信任 MOA 返回值；"
            "未验证 v2/gift/send，收礼方可能仍未到账。",
            file=sys.stderr,
        )
        return 0

    summary["success"] = False
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if moa_send_ok:
        print(
            "MOA sendMiddlePackageGift 返回 true，但未触发真实送礼（无 v2/gift/send）。"
            "请用 ADB 从送礼方背包送出，Tunnel 验收 gift/send ec=200。",
            file=sys.stderr,
        )
    else:
        print("背包送礼失败：sendMiddlePackageGift 返回 result 非 true", file=sys.stderr)
    return 3
