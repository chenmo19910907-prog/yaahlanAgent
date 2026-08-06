#!/usr/bin/env python3
"""Stage environment gift send: CMDB -> MOA gift/user -> POST /v2/gift/send."""

from __future__ import annotations

import argparse
import json
import os
import random
import socket
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


def _project_app() -> tuple[int, str]:
    try:
        import sys
        from pathlib import Path

        platform_dir = Path(__file__).resolve().parents[2] / "platform"
        if str(platform_dir) not in sys.path:
            sys.path.insert(0, str(platform_dir))
        from project.loader import app_id, cmdb_instances_url

        return app_id(), cmdb_instances_url()
    except (ImportError, FileNotFoundError, ValueError, OSError):
        return 2005, (
            "http://cmdb.momo.com/open/hubble-app-instances/"
            "?appkey=momo.ibt.yaahlan.service.yaahlan-web&corp=alpha&env=stage"
        )


def _app_id() -> int:
    return _project_app()[0]


def _cmdb_url() -> str:
    return _project_app()[1]


APP_ID = _app_id()
CMDB_URL = _cmdb_url()
DEFAULT_CMDB_TOKEN = "61430279892c78e0587d58b338288ac06e7641fb"
DEFAULT_PACKAGE_ID = "12321312"
MOA_LOOKUP_HOST = "moa_lookup_alpha.momo.com"
MOA_LOOKUP_PORT = 10010
GIFT_SERVICE_URI = "/service/mdp-gift/gift-query-service"
USER_PROFILE_URI = "/service/voga-mts-user-profile-stage"
PAY_SERVICE_URI = "/service/voga-base-service-middle-pay-stage"
VIP_SERVICE_URI = "/service/voga-mts-user-vip-stage"

DIAMOND_PROVIDE_DEFAULTS = {
    "activityId": "2005000496",
    "taskId": "2005000497",
    "signKey": "189ad0ec4e41438abf29e2f2874d94eb",
    "outOrderIdPrefix": "system",
}

PRODUCT_TYPE_MAP = {
    (0, 0): "NORMAL_DEFAULT",
    (0, 1): "NORMAL_BLIND_BOX",
    (0, 2): "NORMAL_BLIND_BOX_RANDOM",
    (0, 3): "NORMAL_LUCK",
    (0, 4): "NORMAL_CP",
    (0, 5): "NORMAL_NEW_LUCK",
    (0, 6): "NORMAL_TRUST_TOKEN",
    (0, 7): "NORMAL_FREE_PRE",
    (0, 8): "NORMAL_PAY_PRE",
    (0, 9): "NORMAL_PAID_FLY_COMMENTS",
    (0, 10): "NORMAL_FREE_DYNAMIC_PRE",
    (0, 11): "NORMAL_PAY_DYNAMIC_PRE",
    (1, 0): "PACK_DEFAULT",
    (2, 0): "PROP_DEFAULT",
}

SCENE_SOURCE = {
    "chatroom": "chatroom",
    "group": "group",
    "private": "im",
}


class StageGiftError(Exception):
    def __init__(self, step: str, message: str):
        super().__init__(message)
        self.step = step
        self.message = message


def emit(result: Dict[str, Any], exit_code: int = 0) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(exit_code)


def emit_error(step: str, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    payload: Dict[str, Any] = {"ok": False, "step": step, "error": message}
    if extra:
        payload.update(extra)
    emit(payload, 1)


def redis_get(host: str, port: int, key: str, timeout: int = 5) -> Optional[str]:
    sock = socket.create_connection((host, port), timeout=timeout)
    try:
        sock.sendall(f"*2\r\n$3\r\nGET\r\n${len(key)}\r\n{key}\r\n".encode())
        buf = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
            if buf.startswith(b"$"):
                idx = buf.index(b"\r\n")
                length = int(buf[1:idx])
                if len(buf) >= idx + 2 + length + 2:
                    break
        if buf.startswith(b"$-1"):
            return None
        if buf.startswith(b"$"):
            idx = buf.index(b"\r\n")
            length = int(buf[1:idx])
            return buf[idx + 2 : idx + 2 + length].decode()
        return buf.decode()
    finally:
        sock.close()


def lookup_provider(service_uri: str, ip: str = "") -> Tuple[str, int]:
    req = {
        "action": "/service/lookup",
        "params": {"m": "getService", "args": [service_uri, "redis"]},
    }
    key = json.dumps(req, separators=(",", ":"))
    raw = redis_get(MOA_LOOKUP_HOST, MOA_LOOKUP_PORT, key)
    if not raw:
        raise StageGiftError("moa_lookup", f"lookup 返回为空: {service_uri}")

    data = json.loads(raw)
    hosts = (data.get("result") or {}).get("hosts") or []
    target = ip.strip()
    for host_entry in hosts:
        address = host_entry.split("?")[0]
        parts = address.split(":")
        if len(parts) != 2:
            continue
        host_ip, host_port = parts[0], int(parts[1])
        if target and host_ip != target:
            continue
        if not target and not host_ip.startswith("10."):
            continue
        return host_ip, host_port
    raise StageGiftError("moa_lookup", f"未找到 provider: {service_uri}")


def call_moa(service_uri: str, method: str, args: List[Any], headers: str = "", ip: str = "") -> Any:
    provider_ip, provider_port = lookup_provider(service_uri, ip)
    req: Dict[str, Any] = {
        "action": service_uri,
        "params": {"m": method, "args": args},
    }
    if headers:
        req["params"]["businessTransportKey"] = headers
    key = json.dumps(req, separators=(",", ":"))
    raw = redis_get(provider_ip, provider_port, key)
    if not raw:
        raise StageGiftError("moa_call", f"MOA 返回为空: {service_uri}.{method}")

    outer = json.loads(raw)
    if outer.get("ec") != 0:
        raise StageGiftError("moa_call", f"MOA 外层失败: {outer.get('em')}")

    result = outer.get("result")
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            pass
    return result


def get_cmdb_token() -> str:
    return (os.environ.get("CMDB_TOKEN") or DEFAULT_CMDB_TOKEN).strip()


def get_instance_ip() -> str:
    token = get_cmdb_token()
    req = urllib.request.Request(CMDB_URL, headers={"Authorization": f"Token {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        raise StageGiftError("cmdb", f"CMDB 请求失败: {exc}") from exc

    if not isinstance(body, list) or not body:
        raise StageGiftError("cmdb", f"CMDB 响应无实例: {body}")

    instance_ip = body[0].get("instance_ip")
    if not instance_ip:
        raise StageGiftError("cmdb", f"CMDB 缺少 instance_ip: {body[0]}")
    return instance_ip


def unwrap_moa_data(result: Any, step: str) -> List[Dict[str, Any]]:
    if isinstance(result, dict):
        ec = result.get("ec")
        if ec not in (0, 200):
            raise StageGiftError(step, f"业务失败 ec={ec} em={result.get('em')}")
        data = result.get("data")
        if isinstance(data, list):
            return data
    raise StageGiftError(step, f"无法解析 MOA 数据: {result}")


def map_request_gift_fields(gift_type: int, gift_sub_type: int) -> Tuple[int, int, str]:
    product = PRODUCT_TYPE_MAP.get((gift_type, gift_sub_type), "UNKNOWN")
    if product == "PROP_DEFAULT":
        return 2, 0, product
    if product == "PACK_DEFAULT":
        return 0, 1, product
    return 0, 0, product


def query_gift(gift_id: str, lang: str = "en") -> Dict[str, Any]:
    product_id = int(gift_id)
    query_param = {"appId": APP_ID, "productIds": [product_id], "lang": lang}

    result = call_moa(GIFT_SERVICE_URI, "batchQueryCategoryPropAndGifts", [query_param])
    try:
        items = unwrap_moa_data(result, "query_gift")
        if items:
            dto = items[0]
            req_gift_type, is_package, product = map_request_gift_fields(
                int(dto.get("giftType", 0)), int(dto.get("giftSubType", 0))
            )
            return {
                "category": dto.get("category"),
                "giftType": req_gift_type,
                "giftSubType": int(dto.get("giftSubType", 0)),
                "isPackage": is_package,
                "productType": product,
                "rawGiftType": int(dto.get("giftType", 0)),
                "productName": dto.get("productName"),
                "price": dto.get("price"),
                "nominalPrice": dto.get("nominalPrice"),
                "source": "batchQueryCategoryPropAndGifts",
            }
    except StageGiftError:
        pass

    prop_result = call_moa(GIFT_SERVICE_URI, "batchQueryCategoryProps", [query_param])
    prop_items = unwrap_moa_data(prop_result, "query_gift_prop")
    if not prop_items:
        raise StageGiftError("query_gift", f"礼物不存在: giftId={gift_id}")
    dto = prop_items[0]
    return {
        "category": dto.get("category"),
        "giftType": 2,
        "giftSubType": int(dto.get("giftSubType", 0)),
        "isPackage": 0,
        "productType": "PROP_DEFAULT",
        "rawGiftType": int(dto.get("giftType", 2)),
        "productName": dto.get("productName"),
        "price": dto.get("price"),
        "nominalPrice": dto.get("nominalPrice"),
        "source": "batchQueryCategoryProps",
    }


def random_out_order_id(prefix: str = "system") -> str:
    return f"{prefix}-{random.randint(10000, 99999)}"


def parse_diamond_count(result: Any) -> int:
    if not isinstance(result, dict):
        raise StageGiftError("diamond_query", f"无法解析钻石余额: {result}")
    diamonds = result.get("diamonds")
    if diamonds is None:
        raise StageGiftError("diamond_query", f"响应缺少 diamonds: {result}")
    return int(diamonds)


def query_diamond_balance(user_id: str) -> int:
    result = call_moa(PAY_SERVICE_URI, "queryUserAccount", [user_id])
    return parse_diamond_count(result)


def parse_vip_exp_value(result: Any) -> int:
    if not isinstance(result, dict):
        raise StageGiftError("vip_query", f"无法解析 VIP 返回: {result}")
    value = result.get("value")
    if value is None:
        raise StageGiftError("vip_query", f"响应缺少 value: {result}")
    return int(value)


def query_vip_exp(user_id: str) -> int:
    result = call_moa(VIP_SERVICE_URI, "getVipInfo", [user_id])
    return parse_vip_exp_value(result)


def provide_diamond(user_id: str, num: int) -> Dict[str, Any]:
    if num <= 0:
        raise StageGiftError("diamond_provide", "充值数量必须为正整数")
    payload = {
        "userId": user_id,
        "num": num,
        "activityId": DIAMOND_PROVIDE_DEFAULTS["activityId"],
        "taskId": DIAMOND_PROVIDE_DEFAULTS["taskId"],
        "outOrderId": random_out_order_id(DIAMOND_PROVIDE_DEFAULTS["outOrderIdPrefix"]),
        "signKey": DIAMOND_PROVIDE_DEFAULTS["signKey"],
    }
    result = call_moa(PAY_SERVICE_URI, "provideDiamond", [payload])
    return {"requested": num, "response": result}


def gift_needs_diamond(gift_meta: Dict[str, Any]) -> bool:
    if gift_meta.get("isPackage") == 1:
        return False
    price = gift_meta.get("price")
    if price is None:
        return True
    return float(price) > 0


def compute_gift_diamond_cost(
    gift_meta: Dict[str, Any],
    num: int,
    receivers: List[str],
    send_room_all: bool,
    snap_data: Optional[Dict[str, Any]],
) -> int:
    if send_room_all and snap_data is not None:
        need = snap_data.get("needDiamonds")
        if need is not None:
            return int(need)

    price = gift_meta.get("price")
    if price is None:
        raise StageGiftError("gift_price", f"礼物缺少 price，无法计算钻石消耗: {gift_meta.get('productName')}")
    unit = int(round(float(price)))
    receiver_count = 1 if send_room_all or not receivers else len(receivers)
    return unit * num * receiver_count


def ensure_diamond_for_gift(sender: str, gift_cost: int) -> Dict[str, Any]:
    balance_before = query_diamond_balance(sender)
    topped_up = 0
    provide_result: Optional[Dict[str, Any]] = None

    if balance_before < gift_cost:
        topped_up = gift_cost
        provide_result = provide_diamond(sender, topped_up)

    balance_before_send = query_diamond_balance(sender)
    if balance_before_send < gift_cost:
        raise StageGiftError(
            "diamond_provide",
            f"充值后余额仍不足: balance={balance_before_send} need={gift_cost}",
        )

    audit: Dict[str, Any] = {
        "gift_cost": gift_cost,
        "balance_before": balance_before,
        "balance_before_send": balance_before_send,
        "topped_up": topped_up,
    }
    if provide_result is not None:
        audit["provide"] = provide_result
    return audit


def verify_diamond_consumed(balance_before_send: int, gift_cost: int, sender: str) -> Dict[str, Any]:
    balance_after = query_diamond_balance(sender)
    consumed = balance_before_send - balance_after
    return {
        "balance_after": balance_after,
        "consumed": consumed,
        "expected": gift_cost,
        "verified": consumed == gift_cost,
    }


def query_user_device(sender: str) -> Dict[str, Any]:
    result = call_moa(USER_PROFILE_URI, "getUserVersionInfo", [{"userId": sender}])
    if isinstance(result, dict) and result.get("userId"):
        device = {
            "ua": result.get("ua") or "",
            "deviceId": result.get("deviceId") or "",
            "osType": result.get("osType") or "android",
            "lang": result.get("lang") or "en",
            "ip": result.get("ip") or "172.18.124.230",
            "appVersion": result.get("appVersion") or "1000",
            "source": "getUserVersionInfo",
        }
    else:
        fallback = call_moa(USER_PROFILE_URI, "getUserInfoByFields", [sender, [], "en"])
        if not isinstance(fallback, dict):
            raise StageGiftError("query_user", f"用户设备信息不存在: userId={sender}")
        device = {
            "ua": fallback.get("ua") or "",
            "deviceId": fallback.get("deviceId") or "",
            "osType": fallback.get("osType") or "android",
            "lang": fallback.get("lang") or fallback.get("initLang") or "en",
            "ip": fallback.get("ip") or "172.18.124.230",
            "appVersion": fallback.get("appVersion") or "1000",
            "source": "getUserInfoByFields",
        }

    os_type = (device.get("osType") or "android").lower()
    device["rom"] = "26.2" if os_type == "ios" else "10"
    device["model"] = "iPhone 11" if os_type == "ios" else "MI8SE"
    device["innerVersion"] = device.get("appVersion") or "1000"
    return device


def build_ext(
    scene: str,
    scene_id: Optional[str],
    receivers: List[str],
    num: int,
    *,
    intimate_invite: bool = False,
) -> str:
    # Client intimate invite capture uses source=p2p + intimate_invite_gift=1
    source = "p2p" if intimate_invite else SCENE_SOURCE[scene]
    ext: Dict[str, Any] = {
        "timeZone": "Asia/Shanghai",
        "source": source,
        "localTime": str(int(time.time() * 1000)),
        "giftNum": num,
    }
    if intimate_invite:
        ext["intimate_invite_gift"] = 1
        ext["feedId"] = ""
    else:
        ext["receiverIds"] = ",".join(receivers)
        ext["fromCursor"] = 1
    if scene == "chatroom" and scene_id:
        ext["room_id"] = scene_id
    return json.dumps(ext, ensure_ascii=False)


def build_payload(
    scene: str,
    sender: str,
    receivers: List[str],
    gift_id: str,
    num: int,
    scene_id: Optional[str],
    gift_meta: Dict[str, Any],
    user_device: Dict[str, Any],
    send_room_all_snap_id: Optional[str] = None,
    intimate_invite: bool = False,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "appId": APP_ID,
        "app_id": None,
        "uid": sender,
        "ip": user_device.get("ip"),
        "deviceId": user_device.get("deviceId"),
        "innerVersion": user_device.get("innerVersion"),
        "rom": user_device.get("rom"),
        "osType": user_device.get("osType"),
        "channelKey": "primary",
        "channel_key": None,
        "model": user_device.get("model"),
        "lat": None,
        "lng": None,
        "lang": user_device.get("lang"),
        "category": gift_meta.get("category"),
        "giftId": gift_id,
        "num": num,
        "isPackage": gift_meta.get("isPackage", 0),
        # Intimate invite capture uses isMulti=0（单人）
        "isMulti": 0 if intimate_invite else 1,
        "ext": build_ext(
            scene, scene_id, receivers, num, intimate_invite=intimate_invite
        ),
        "ua": user_device.get("ua"),
        "giftType": gift_meta.get("giftType", 0),
        "giftSubType": gift_meta.get("giftSubType", 0),
    }
    if send_room_all_snap_id:
        payload["sendRoomAllSnapId"] = send_room_all_snap_id
    else:
        # Match client intimate invite: remoteIdList as JSON string of string ids
        if intimate_invite:
            payload["remoteIdList"] = json.dumps(
                [str(r) for r in receivers], separators=(",", ":")
            )
            payload["sceneId"] = ""
        else:
            remote_ids = [int(r) if r.isdigit() else r for r in receivers]
            payload["remoteIdList"] = json.dumps(remote_ids, separators=(",", ":"))
    if (not intimate_invite) and scene in ("chatroom", "group") and scene_id:
        payload["sceneId"] = scene_id
    return payload


def is_success_response(response: Dict[str, Any]) -> bool:
    if response.get("success") is True:
        return True
    ec = response.get("ec")
    return ec in (0, 200)


def http_post(instance_ip: str, path: str, sender: str, package_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"http://{instance_ip}:8080{path}"
    body = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "userId": sender,
            "package-id": package_id,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise StageGiftError("http_post", f"HTTP {exc.code} {path}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise StageGiftError("http_post", f"请求失败 {path}: {exc}") from exc


def post_gift(instance_ip: str, sender: str, package_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return http_post(instance_ip, "/v2/gift/send", sender, package_id, payload)


def get_send_room_all_snap(
    instance_ip: str, sender: str, package_id: str, scene_id: str, gift_id: str, num: int
) -> Dict[str, Any]:
    payload = {"sceneId": scene_id, "giftId": gift_id, "num": num}
    resp = http_post(instance_ip, "/v2/gift/getSendRoomAllSnap", sender, package_id, payload)
    if not isinstance(resp, dict):
        raise StageGiftError("get_snap", f"getSendRoomAllSnap unexpected response: {resp}")
    ec = resp.get("ec")
    if ec not in (0, 200, None):
        raise StageGiftError("get_snap", f"getSendRoomAllSnap failed ec={ec} em={resp.get('em')}")
    data = resp.get("data")
    if not isinstance(data, dict) or not data.get("snapId"):
        raise StageGiftError("get_snap", f"getSendRoomAllSnap no snapId in response: {resp}")
    return data


def parse_receivers(raw: str) -> List[str]:
    receivers = [item.strip() for item in raw.split(",") if item.strip()]
    if not receivers:
        raise StageGiftError("args", "receivers 不能为空")
    return receivers


def validate_scene(scene: str, scene_id: Optional[str]) -> None:
    if scene not in SCENE_SOURCE:
        raise StageGiftError("args", f"未知 scene: {scene}")
    if scene in ("chatroom", "group") and not scene_id:
        raise StageGiftError("args", f"scene={scene} 时必须提供 --scene-id")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage gift send for yaahlan-web")
    parser.add_argument("--scene", required=True, choices=sorted(SCENE_SOURCE.keys()))
    parser.add_argument("--sender", required=True, help="送礼人 userId")
    parser.add_argument("--receivers", default="", help="收礼人，逗号分隔（全房间送礼时可不传）")
    parser.add_argument("--gift-id", required=True, help="礼物 productId")
    parser.add_argument("--scene-id", help="roomId 或 groupId")
    parser.add_argument("--num", type=int, default=1, help="礼物数量，默认 1")
    parser.add_argument("--package-id", default=DEFAULT_PACKAGE_ID, help="HTTP header package-id")
    parser.add_argument("--dry-run", action="store_true", help="只组装 payload，不 POST")
    parser.add_argument("--probe", action="store_true", help="只探测 CMDB/MOA，不 POST")
    parser.add_argument(
        "--send-room-all",
        action="store_true",
        help="全房间送礼，自动调用 getSendRoomAllSnap 获取 snapId",
    )
    parser.add_argument(
        "--intimate-invite",
        action="store_true",
        help="亲密关系申请送礼：ext.intimate_invite_gift=1 + source=p2p（抓包复现；建议 --scene private）",
    )
    return parser


def run(args: argparse.Namespace) -> None:
    validate_scene(args.scene, args.scene_id)
    send_room_all = args.send_room_all
    intimate_invite = bool(args.intimate_invite)
    if intimate_invite and send_room_all:
        raise StageGiftError("args", "--intimate-invite 不能与 --send-room-all 同时使用")
    if intimate_invite and args.scene != "private":
        raise StageGiftError(
            "args",
            "--intimate-invite 须配合 --scene private（端上为 p2p 私聊送礼）",
        )
    receivers = [] if send_room_all else parse_receivers(args.receivers)
    if intimate_invite and len(receivers) != 1:
        raise StageGiftError("args", "--intimate-invite 仅支持 1 个收礼人")

    instance_ip = get_instance_ip()
    gift_meta = query_gift(args.gift_id)
    user_device = query_user_device(args.sender)

    snap_data: Optional[Dict[str, Any]] = None
    snap_id: Optional[str] = None
    if send_room_all:
        snap_data = get_send_room_all_snap(
            instance_ip, args.sender, args.package_id, args.scene_id, args.gift_id, args.num
        )
        snap_id = snap_data["snapId"]

    payload = build_payload(
        args.scene,
        args.sender,
        receivers,
        args.gift_id,
        args.num,
        args.scene_id,
        gift_meta,
        user_device,
        send_room_all_snap_id=snap_id,
        intimate_invite=intimate_invite,
    )

    result: Dict[str, Any] = {
        "ok": True,
        "instance_ip": instance_ip,
        "gift_meta": gift_meta,
        "user_device": user_device,
        "request": payload,
        "intimate_invite": intimate_invite,
    }
    if snap_data:
        result["snap"] = snap_data

    if args.probe:
        result["mode"] = "probe"
        emit(result)
        return

    if args.dry_run:
        result["mode"] = "dry-run"
        emit(result)
        return

    diamond_audit: Optional[Dict[str, Any]] = None
    gift_cost = 0
    if gift_needs_diamond(gift_meta):
        gift_cost = compute_gift_diamond_cost(
            gift_meta, args.num, receivers, send_room_all, snap_data
        )
        diamond_audit = ensure_diamond_for_gift(args.sender, gift_cost)
        result["diamond"] = diamond_audit

    response = post_gift(instance_ip, args.sender, args.package_id, payload)
    result["response"] = response
    result["mode"] = "execute"
    if isinstance(response, dict) and not is_success_response(response):
        result["ok"] = False
        result["step"] = "post_gift"
        result["error"] = response.get("em") or str(response)
        emit(result, 1)

    if diamond_audit is not None:
        verification = verify_diamond_consumed(
            diamond_audit["balance_before_send"], gift_cost, args.sender
        )
        result["diamond"]["after_send"] = verification
        if not verification["verified"]:
            result["ok"] = False
            result["step"] = "diamond_verify"
            result["error"] = (
                f"钻石消耗不符: 期望 {gift_cost}，实际消耗 {verification['consumed']}，"
                f"送礼前 {diamond_audit['balance_before_send']} → 送礼后 {verification['balance_after']}"
            )
            emit(result, 1)

    emit(result)


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    if ns.send_room_all:
        if ns.scene != "chatroom":
            emit_error("args", "全房间送礼仅支持 chatroom 场景")
            return 1
        if not ns.scene_id:
            emit_error("args", "全房间送礼需要 --scene-id (roomId)")
            return 1
    elif not ns.receivers:
        emit_error("args", "非全房间送礼必须提供 --receivers")
        return 1
    try:
        run(ns)
    except StageGiftError as exc:
        emit_error(exc.step, exc.message)
        return 1
    return 0
