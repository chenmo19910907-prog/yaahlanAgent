#!/usr/bin/env python3
import argparse
import json
import os
import random
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


def _load_local_env() -> None:
    """
    从仓库内的 MOA/.env.local 读取环境变量（仅本机使用，已在 .gitignore 忽略）。
    文件格式为 KEY=VALUE，每行一条；忽略空行和 # 注释。
    """
    # 以脚本所在目录为基准，避免 cwd 影响
    base_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(base_dir, ".env.local")
    if not os.path.exists(env_path):
        return

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                # 不 strip v，保留 cookie 里可能的空格（如果用户复制带空格）
                if not k:
                    continue
                # 不覆盖已存在的环境变量（命令行 export 优先）
                os.environ.setdefault(k, v)
    except Exception:
        # 读取失败不应阻断主流程
        return


_CONFIG_CACHE: Optional[Dict[str, Any]] = None


def _default_config() -> Dict[str, Any]:
    return {
        "room_level_exp_thresholds": {
            "1": 0,
            "2": 200000,
            "3": 1000000,
            "4": 4500000,
            "5": 18000000,
            "6": 63000000,
            "7": 189000000,
        }
    }


def _load_config() -> Dict[str, Any]:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    base_dir = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(base_dir, "config.json")
    cfg: Dict[str, Any] = _default_config()
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except Exception:
            # 配置解析失败时回退默认配置，不阻断主流程
            cfg = _default_config()

    _CONFIG_CACHE = cfg
    return cfg


def _room_level_thresholds() -> dict[int, int]:
    cfg = _load_config()
    raw = cfg.get("room_level_exp_thresholds")
    if not isinstance(raw, dict):
        raise RuntimeError("配置错误：room_level_exp_thresholds 必须是 object")
    thresholds: dict[int, int] = {}
    for k, v in raw.items():
        try:
            lv = int(k)
            exp = int(v)
        except Exception:
            raise RuntimeError(f"配置错误：room_level_exp_thresholds 键值必须可转为 int: {k}={v}")
        thresholds[lv] = exp
    if not thresholds:
        raise RuntimeError("配置错误：room_level_exp_thresholds 不能为空")
    return thresholds


def _vip_level_thresholds() -> dict[int, int]:
    cfg = _load_config()
    raw = cfg.get("vip_level_exp_thresholds")
    if not isinstance(raw, dict):
        raise RuntimeError("配置错误：vip_level_exp_thresholds 必须是 object")
    thresholds: dict[int, int] = {}
    for k, v in raw.items():
        try:
            lv = int(k)
            exp = int(v)
        except Exception:
            raise RuntimeError(f"配置错误：vip_level_exp_thresholds 键值必须可转为 int: {k}={v}")
        thresholds[lv] = exp
    if not thresholds:
        raise RuntimeError("配置错误：vip_level_exp_thresholds 不能为空")
    return thresholds


def _build_room_exp_expr(room_id: str, exp: int) -> str:
    room_id = str(room_id).strip()
    if not room_id:
        raise ValueError("room_id 不能为空")
    if exp < 0:
        raise ValueError("exp 不能为负数")
    return f'context.getBean("roomProfileDao").addRoomActiveValue("{room_id}",{exp}D)'


def _build_room_exp_delta_for_level(level: int, current_exp: int) -> int:
    thresholds = _room_level_thresholds()
    if level not in thresholds:
        raise ValueError(f"不支持的房间等级: {level}，支持范围: {sorted(thresholds.keys())}")
    if current_exp < 0:
        raise ValueError("current_exp 不能为负数")
    target = thresholds[level]
    delta = target - current_exp
    if delta <= 0:
        raise ValueError(f"当前经验值已 >= 目标等级阈值：current_exp={current_exp}, target={target}")
    return delta


def _build_vip_exp_delta_for_level(level: int, current_exp: int) -> int:
    thresholds = _vip_level_thresholds()
    if level not in thresholds:
        raise ValueError(f"不支持的 VIP 等级: {level}，支持范围: {sorted(thresholds.keys())}")
    if current_exp < 0:
        raise ValueError("current_exp 不能为负数")
    target = thresholds[level]
    delta = target - current_exp
    if delta <= 0:
        raise ValueError(f"当前 VIP 经验值已 >= 目标等级阈值：current_exp={current_exp}, target={target}")
    return delta


def _level_by_exp(exp: int) -> int:
    if exp < 0:
        raise ValueError("exp 不能为负数")
    # 返回满足阈值的最高等级
    thresholds = _room_level_thresholds()
    level = 1
    for lv in sorted(thresholds.keys()):
        if exp >= thresholds[lv]:
            level = lv
    return level


def _vip_level_by_exp(exp: int) -> int:
    if exp < 0:
        raise ValueError("exp 不能为负数")
    thresholds = _vip_level_thresholds()
    level = min(thresholds.keys())
    for lv in sorted(thresholds.keys()):
        if exp >= thresholds[lv]:
            level = lv
    return level


def _set_vip_params(payload: Dict[str, Any], user_id: str, vip_exp_delta: int) -> None:
    if vip_exp_delta < 0:
        raise ValueError("vip_exp_delta 不能为负数")
    payload["params"] = [
        {
            "title": "参数1",
            "name": "1",
            "txt": str(user_id),
            "json": "",
            "type": "string",
            "value": str(user_id),
        },
        {
            "title": "参数2",
            "name": "2",
            "txt": str(vip_exp_delta),
            "json": "",
            "type": "int",
            "value": str(vip_exp_delta),
        },
    ]


def _random_five_digit_out_order_id(prefix: str = "system") -> str:
    return f"{prefix}-{random.randint(10000, 99999)}"


def _random_thirteen_digit() -> int:
    return random.randint(10**12, 10**13 - 1)


def _random_package_gift_out_order_id(prefix: str, middle: str) -> str:
    return f"{prefix}-{middle}-{_random_thirteen_digit()}"


def _diamond_provide_defaults() -> dict[str, str]:
    cfg = _load_config()
    raw = cfg.get("diamond_provide")
    if not isinstance(raw, dict):
        return {
            "activityId": "2005000496",
            "taskId": "2005000497",
            "signKey": "189ad0ec4e41438abf29e2f2874d94eb",
            "outOrderIdPrefix": "system",
        }
    return {
        "activityId": str(raw.get("activityId", "2005000496")),
        "taskId": str(raw.get("taskId", "2005000497")),
        "signKey": str(raw.get("signKey", "189ad0ec4e41438abf29e2f2874d94eb")),
        "outOrderIdPrefix": str(raw.get("outOrderIdPrefix", "system")),
    }


def _set_diamond_provide_params(
    payload: Dict[str, Any],
    user_id: str,
    num: int,
    *,
    out_order_id: Optional[str] = None,
    activity_id: Optional[str] = None,
    task_id: Optional[str] = None,
    sign_key: Optional[str] = None,
) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    if num <= 0:
        raise ValueError("num 必须为正整数（钻石数量）")

    defaults = _diamond_provide_defaults()
    if out_order_id is None:
        out_order_id = _random_five_digit_out_order_id(defaults["outOrderIdPrefix"])
    if activity_id is None:
        activity_id = defaults["activityId"]
    if task_id is None:
        task_id = defaults["taskId"]
    if sign_key is None:
        sign_key = defaults["signKey"]

    value = {
        "userId": user_id,
        "num": num,
        "activityId": activity_id,
        "taskId": task_id,
        "outOrderId": out_order_id,
        "signKey": sign_key,
    }
    payload["params"] = [
        {
            "title": "参数1",
            "name": "1",
            "txt": value,
            "json": json.dumps(value, ensure_ascii=False, separators=(",", ":")),
            "type": "json",
            "value": value,
        }
    ]


def _package_gift_defaults() -> dict[str, Any]:
    cfg = _load_config()
    raw = cfg.get("package_gift")
    default_gifts = [
        {"baseProductId": "2005001272", "productNum": 100},
        {"baseProductId": "2005001282", "productNum": 100},
    ]
    if not isinstance(raw, dict):
        return {
            "outOrderIdPrefix": "PACKAGE_GIFT",
            "outOrderIdMiddle": "100328136",
            "category": "2005000189",
            "source": 2005001287,
            "signKey": "76b26f6deb1e4851b728e3b0770629db",
            "realFee": "0",
            "expireSeconds": 86339,
            "giftDetails": default_gifts,
        }
    gifts = raw.get("giftDetails")
    if not isinstance(gifts, list) or not gifts:
        gifts = default_gifts
    return {
        "outOrderIdPrefix": str(raw.get("outOrderIdPrefix", "PACKAGE_GIFT")),
        "outOrderIdMiddle": str(raw.get("outOrderIdMiddle", "100328136")),
        "category": str(raw.get("category", "2005000189")),
        "source": int(raw.get("source", 2005001287)),
        "signKey": str(raw.get("signKey", "76b26f6deb1e4851b728e3b0770629db")),
        "realFee": str(raw.get("realFee", "0")),
        "expireSeconds": int(raw.get("expireSeconds", 86339)),
        "giftDetails": gifts,
    }


def _set_package_gift_params(
    payload: Dict[str, Any],
    user_id: str,
    *,
    product_num: Optional[int] = None,
    give_user_id: str = "",
    out_order_id: Optional[str] = None,
) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")

    defaults = _package_gift_defaults()
    if out_order_id is None:
        out_order_id = _random_package_gift_out_order_id(
            defaults["outOrderIdPrefix"],
            defaults["outOrderIdMiddle"],
        )

    gift_details: list[dict[str, Any]] = []
    for item in defaults["giftDetails"]:
        if not isinstance(item, dict):
            continue
        base_id = item.get("baseProductId")
        if base_id is None:
            continue
        num = product_num if product_num is not None else item.get("productNum", 100)
        try:
            num_int = int(num)
        except (TypeError, ValueError) as e:
            raise ValueError(f"gift productNum 无效: {num}") from e
        if num_int <= 0:
            raise ValueError("gift productNum 必须为正整数")
        gift_details.append({"baseProductId": str(base_id), "productNum": num_int})

    if not gift_details:
        raise ValueError("package_gift.giftDetails 配置为空或无效")

    value = {
        "userId": user_id,
        "giveUserId": give_user_id,
        "outOrderId": out_order_id,
        "category": defaults["category"],
        "source": defaults["source"],
        "giftDetails": gift_details,
        "realFee": defaults["realFee"],
        "expireSeconds": defaults["expireSeconds"],
        "signKey": defaults["signKey"],
    }
    payload["params"] = [
        {
            "title": "参数1",
            "name": "1",
            "txt": value,
            "json": json.dumps(value, ensure_ascii=False, separators=(",", ":")),
            "type": "json",
            "value": value,
        }
    ]


def _set_vip_del_params(payload: Dict[str, Any], user_id: str) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    payload["params"] = [
        {
            "title": "参数1",
            "name": "1",
            "txt": user_id,
            "json": "",
            "type": "string",
            "value": user_id,
        }
    ]


def _set_id_auth_params(payload: Dict[str, Any], user_id: str) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    payload["params"] = [
        {
            "title": "参数1",
            "name": "1",
            "txt": {"userId": user_id},
            "json": json.dumps({"userId": user_id}, ensure_ascii=False, separators=(",", ":")),
            "type": "json",
            "value": {"userId": user_id},
        }
    ]


def _set_id_auth_reset_expire_params(payload: Dict[str, Any], user_id: str, expire_ms: int) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    if expire_ms <= 0:
        raise ValueError("expire_ms 必须为正整数（毫秒时间戳）")
    payload["params"] = [
        {"title": "参数1", "name": "1", "txt": user_id, "json": "", "type": "string", "value": user_id},
        {"title": "参数2", "name": "2", "txt": str(expire_ms), "json": "", "type": "long", "value": str(expire_ms)},
    ]


def _set_id_auth_delete_person_params(payload: Dict[str, Any], user_id: str) -> None:
    user_id = str(user_id).strip()
    if not user_id:
        raise ValueError("user_id 不能为空")
    payload["params"] = [
        {"title": "参数1", "name": "1", "txt": user_id, "json": "", "type": "string", "value": user_id},
    ]


def _extract_latest_id_auth_reason_list(inner_result: Any) -> list[str]:
    """
    从 queryRealPersonRecord 的业务返回中提取最近一条记录的 reason，并解析成 userId 列表。
    reason 在历史数据中可能为：
    - 空字符串
    - JSON 字符串数组，如 "[\"100486375\"]"
    - 真实 list，如 ["100486375"]
    """
    if not isinstance(inner_result, dict):
        raise RuntimeError("无法解析实名认证业务返回 result（不是 object）")
    data = inner_result.get("data")
    if not isinstance(data, dict):
        return []
    lst = data.get("list")
    if not isinstance(lst, list) or not lst:
        return []
    reason = lst[0].get("reason")
    if reason is None:
        return []
    if isinstance(reason, list):
        return [str(x) for x in reason if str(x).strip()]
    if isinstance(reason, str):
        s = reason.strip()
        if not s:
            return []
        # 尝试解析 JSON 数组字符串
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if str(x).strip()]
        except Exception:
            pass
        return [s]
    return [str(reason)]


def _load_payload(args: argparse.Namespace) -> Dict[str, Any]:
    if args.payload_file:
        with open(args.payload_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
    elif args.payload:
        payload = json.loads(args.payload)
    else:
        raise ValueError("必须提供 --payload-file 或 --payload")

    if not isinstance(payload, dict):
        raise ValueError("payload 必须是 JSON object")

    # 顶层字段对齐（与 MOA 导出的 JSON 一致）
    if args.service_url is not None:
        payload["url"] = args.service_url
    if args.moa_method is not None:
        payload["method"] = args.moa_method
    if args.region is not None:
        payload["region"] = args.region
    if args.env is not None:
        payload["env"] = args.env
    if args.cluster is not None:
        payload["cluster"] = args.cluster
    if args.server is not None:
        payload["server"] = args.server
    if args.momo_id is not None:
        payload["momoId"] = args.momo_id
    if args.momo_name is not None:
        payload["momoName"] = args.momo_name
    if args.header is not None:
        payload["header"] = args.header

    if args.host is not None:
        settings = payload.get("settings")
        if settings is None:
            settings = {}
            payload["settings"] = settings
        if not isinstance(settings, dict):
            raise ValueError("payload.settings 必须是 object，才能使用 --host 覆盖")
        settings["host"] = args.host
    if args.moa_time is not None:
        settings = payload.get("settings")
        if settings is None:
            settings = {}
            payload["settings"] = settings
        if not isinstance(settings, dict):
            raise ValueError("payload.settings 必须是 object，才能使用 --moa-time 覆盖")
        settings["time"] = str(args.moa_time)
    if args.group is not None:
        settings = payload.get("settings")
        if settings is None:
            settings = {}
            payload["settings"] = settings
        if not isinstance(settings, dict):
            raise ValueError("payload.settings 必须是 object，才能使用 --group 覆盖")
        settings["group"] = args.group
    if args.header_type is not None:
        settings = payload.get("settings")
        if settings is None:
            settings = {}
            payload["settings"] = settings
        if not isinstance(settings, dict):
            raise ValueError("payload.settings 必须是 object，才能使用 --header-type 覆盖")
        settings["headerType"] = args.header_type

    # 实名认证查询：internal/user/id-auth-api queryRealPersonRecord
    if args.id_auth_user_id is not None:
        payload["url"] = "/service/internal/user/id-auth-api"
        payload["method"] = "queryRealPersonRecord"
        _set_id_auth_params(payload, user_id=args.id_auth_user_id)
        return payload

    # 实名认证：设置认证过期时间 resetRelationPersonExpireTime
    if args.id_auth_reset_expire_user_id is not None:
        payload["url"] = "/service/internal/user/id-auth-api"
        payload["method"] = "resetRelationPersonExpireTime"
        if args.id_auth_expire_ms is None:
            raise ValueError("必须提供 --id-auth-expire-ms（毫秒时间戳）")
        expire_ms = args.id_auth_expire_ms
        _set_id_auth_reset_expire_params(payload, user_id=args.id_auth_reset_expire_user_id, expire_ms=expire_ms)
        return payload

    # 实名认证：清除用户认证信息 internalAuthDeletePerson
    if args.id_auth_delete_user_id is not None:
        payload["url"] = "/service/internal/user/id-auth-api"
        payload["method"] = "internalAuthDeletePerson"
        _set_id_auth_delete_person_params(payload, user_id=args.id_auth_delete_user_id)
        return payload

    # VIP：清除 VIP 信息 delVipInfo
    if args.vip_del_user_id is not None:
        payload["url"] = "/service/voga-mts-user-vip-stage"
        payload["method"] = "delVipInfo"
        _set_vip_del_params(payload, user_id=args.vip_del_user_id)
        return payload

    # 钻石发放：provideDiamond
    if args.diamond_user_id is not None:
        payload["url"] = "/service/voga-base-service-middle-pay-stage"
        payload["method"] = "provideDiamond"
        if args.diamond_num is None:
            raise ValueError("必须提供 --diamond-num（钻石数量）")
        _set_diamond_provide_params(payload, user_id=args.diamond_user_id, num=args.diamond_num)
        return payload

    # 背包礼物下发：addPackageGift
    if args.package_gift_user_id is not None:
        payload["url"] = "/service/voga-base-service-middle-gift-stage"
        payload["method"] = "addPackageGift"
        _set_package_gift_params(
            payload,
            user_id=args.package_gift_user_id,
            product_num=args.package_gift_num,
            give_user_id=args.package_gift_give_user_id or "",
        )
        return payload

    # VIP 模式：用 params[0]=userId, params[1]=vipExpDelta
    if args.vip_user_id is not None:
        # 默认对齐你抓包里的 service/method（也可被 --service-url/--moa-method 覆盖）
        payload.setdefault("url", "/service/voga-mts-user-vip-stage")
        payload.setdefault("method", "addVipValue")

        if args.vip_query_current:
            _set_vip_params(payload, user_id=args.vip_user_id, vip_exp_delta=0)
            return payload

        if args.vip_exp is not None:
            if args.vip_exp < 0:
                raise ValueError("vip_exp 不能为负数")
            _set_vip_params(payload, user_id=args.vip_user_id, vip_exp_delta=args.vip_exp)
            return payload

        if args.vip_level is not None:
            current = args.vip_current_exp if args.vip_current_exp is not None else 0
            delta = _build_vip_exp_delta_for_level(args.vip_level, current_exp=current)
            _set_vip_params(payload, user_id=args.vip_user_id, vip_exp_delta=delta)
            return payload

        raise ValueError("提供了 --vip-user-id 时，必须同时提供 --vip-exp 或 --vip-level 或 --vip-query-current")

    expr: Optional[str] = None
    if args.expr is not None:
        expr = args.expr
    elif args.room_id is not None:
        # 查询模式：通过 addRoomActiveValue(roomId, 0D) 获取当前经验值
        if args.query_current is True:
            expr = _build_room_exp_expr(args.room_id, 0)
        # 便捷模式 1：直接指定增量 exp
        elif args.exp is not None:
            expr = _build_room_exp_expr(args.room_id, args.exp)
        # 便捷模式 2：指定目标 level，脚本根据阈值计算需要增加多少
        elif args.level is not None:
            current = args.current_exp if args.current_exp is not None else 0
            delta = _build_room_exp_delta_for_level(args.level, current_exp=current)
            expr = _build_room_exp_expr(args.room_id, delta)
        elif args.level is None and args.exp is None:
            raise ValueError("提供了 --room-id 时，必须同时提供 --exp 或 --level")
    elif args.exp is not None or args.level is not None:
        raise ValueError("使用 --exp/--level 时必须提供 --room-id")

    if expr is not None:
        params = payload.get("params")
        if not isinstance(params, list) or not params:
            raise ValueError("payload.params 必须是非空数组，才能覆盖 params[0].value/txt")
        if not isinstance(params[0], dict):
            raise ValueError("payload.params[0] 必须是 object，才能覆盖 params[0].value/txt")
        params[0]["value"] = expr
        params[0]["txt"] = expr

    return payload


def _http_post_json(url: str, cookie: str, payload: Dict[str, Any], timeout_s: float) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Cookie": cookie,
    }
    request_source = os.environ.get("MOA_REQUEST_SOURCE")
    if request_source:
        headers["request-source"] = request_source
    origin = os.environ.get("MOA_ORIGIN")
    referer = os.environ.get("MOA_REFERER")
    ua = os.environ.get("MOA_USER_AGENT")
    if origin:
        headers["Origin"] = origin
    if referer:
        headers["Referer"] = referer
    if ua:
        headers["User-Agent"] = ua

    req = urllib.request.Request(
        url=url,
        data=body,
        method="POST",
        headers=headers,
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
        raise RuntimeError(f"HTTP {e.code}: {raw}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误: {e}") from e

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"返回不是合法 JSON: {raw[:1000]}")

    if not isinstance(obj, dict):
        raise RuntimeError("返回 JSON 不是 object")
    return obj


def _extract_ec_em_result(resp: Dict[str, Any]) -> tuple[Optional[int], Optional[str], Any]:
    ec = resp.get("ec")
    em = resp.get("em")
    result = resp.get("result")

    if isinstance(ec, bool):
        ec = int(ec)
    if ec is not None and not isinstance(ec, int):
        try:
            ec = int(ec)
        except Exception:
            ec = None
    if em is not None and not isinstance(em, str):
        em = str(em)
    return ec, em, result


def _outer_success(ec: Optional[int]) -> bool:
    # 该 httpproxy 返回外层 ec 既可能是 0，也可能是 200（ok）
    return ec in (0, 200)


def _extract_inner_result(resp: Dict[str, Any]) -> tuple[int, str, Any]:
    inner = resp.get("result")
    if not isinstance(inner, dict):
        raise RuntimeError("业务返回 result 字段不是 object")
    inner_ec = inner.get("ec")
    inner_em = inner.get("em")
    inner_result = inner.get("result")
    try:
        inner_ec_int = int(inner_ec)
    except Exception:
        raise RuntimeError(f"无法解析业务 ec: {inner_ec}")
    inner_em_str = inner_em if isinstance(inner_em, str) else str(inner_em)
    return inner_ec_int, inner_em_str, inner_result


def _parse_current_exp_from_inner(inner_result: Any) -> int:
    try:
        return int(float(inner_result))
    except Exception as e:
        raise RuntimeError(f"无法解析当前经验值: {inner_result}") from e


def main() -> int:
    _load_local_env()
    parser = argparse.ArgumentParser(description="在本地复现 MOA httpproxy execute 调用")
    parser.add_argument("--entry-url", default=os.environ.get("MOA_ENTRY_URL"), help="httpproxy 入口完整 URL（也可用环境变量 MOA_ENTRY_URL）")
    parser.add_argument("--cookie", default=os.environ.get("MOA_COOKIE"), help="Cookie（也可用环境变量 MOA_COOKIE）")
    parser.add_argument("--timeout-ms", type=int, default=5000, help="HTTP 超时（毫秒），默认 5000")
    parser.add_argument("--host", help='覆盖 payload.settings.host，例如 "10.247.244.119:29584"')
    parser.add_argument("--moa-time", type=int, help='覆盖 payload.settings.time（毫秒），例如 2000/5000')
    parser.add_argument("--group", help='覆盖 payload.settings.group，例如 "default"')
    parser.add_argument("--header-type", help='覆盖 payload.settings.headerType，例如 "TXT"')
    parser.add_argument("--service-url", help='覆盖 payload.url，例如 "/service/yoga-mts-room-backdoor"')
    parser.add_argument("--moa-method", help='覆盖 payload.method，例如 "execute"')
    parser.add_argument("--region", help='覆盖 payload.region，例如 "alpha"')
    parser.add_argument("--env", help='覆盖 payload.env，例如 "alpha"')
    parser.add_argument("--cluster", help='覆盖 payload.cluster，例如 "stage"')
    parser.add_argument("--server", help='覆盖 payload.server，例如 "config"')
    parser.add_argument("--momo-id", help="覆盖 payload.momoId")
    parser.add_argument("--momo-name", help="覆盖 payload.momoName")
    parser.add_argument("--header", help="覆盖 payload.header（通常为空字符串）")
    parser.add_argument("--dump-payload", action="store_true", help="把最终请求 payload（不含 cookie）输出到 stderr，便于对比 MOA")
    parser.add_argument("--origin", default=os.environ.get("MOA_ORIGIN"), help="可选：Origin（也可用环境变量 MOA_ORIGIN）")
    parser.add_argument("--referer", default=os.environ.get("MOA_REFERER"), help="可选：Referer（也可用环境变量 MOA_REFERER）")
    parser.add_argument("--user-agent", default=os.environ.get("MOA_USER_AGENT"), help="可选：User-Agent（也可用环境变量 MOA_USER_AGENT）")
    parser.add_argument("--request-source", default=os.environ.get("MOA_REQUEST_SOURCE"), help='可选：request-source（也可用环境变量 MOA_REQUEST_SOURCE），例如 "moaProxy"')

    src = parser.add_mutually_exclusive_group(required=False)
    src.add_argument("--payload-file", help="包含完整 payload 的 JSON 文件路径")
    src.add_argument("--payload", help="完整 payload JSON 字符串")

    parser.add_argument("--expr", help='覆盖 payload.params[0].value / txt 的表达式，例如 context.getBean("x").y(...)')
    parser.add_argument("--room-id", help='便捷参数：房间 ID（用于生成 addRoomActiveValue 表达式）')
    parser.add_argument("--exp", type=int, help="便捷参数：增加的经验值（正整数，用于生成 addRoomActiveValue 表达式）")
    parser.add_argument("--level", type=int, help="便捷参数：目标房间等级（按内置等级阈值计算需要增加的经验值）")
    parser.add_argument("--current-exp", type=int, help="便捷参数：当前房间经验值（用于配合 --level 计算增量；不传默认按 0 处理）")
    parser.add_argument("--query-current", action="store_true", help="查询当前经验值与等级（通过 addRoomActiveValue(roomId,0D)）")

    # VIP：userId + 增量 / 目标等级（按配置阈值）
    parser.add_argument("--vip-user-id", help="VIP 经验操作：用户ID（对应 addVipValue 的参数1）")
    parser.add_argument("--vip-exp", type=int, help="VIP 经验操作：增加的 VIP 经验值（>=0，对应 addVipValue 的参数2）")
    parser.add_argument("--vip-level", type=int, help="VIP 经验操作：目标 VIP 等级（按阈值计算需要增加的经验值）")
    parser.add_argument("--vip-current-exp", type=int, help="VIP 经验操作：当前 VIP 经验值（配合 --vip-level 计算增量；不传默认按 0 处理）")
    parser.add_argument("--vip-query-current", action="store_true", help="查询当前 VIP 经验值与等级（通过 addVipValue(userId,0)）")
    parser.add_argument("--vip-del-user-id", help="VIP 经验操作：清除 VIP 等级信息（delVipInfo）")

    # 实名认证
    parser.add_argument("--id-auth-user-id", help="查询实名认证记录：userId（调用 queryRealPersonRecord）")
    parser.add_argument(
        "--id-auth-output",
        choices=["latest-reason", "json"],
        default="latest-reason",
        help="实名认证查询输出格式：latest-reason=仅输出最近一条reason（默认）；json=输出完整响应JSON",
    )
    parser.add_argument("--id-auth-reset-expire-user-id", help="设置认证过期时间：userId（resetRelationPersonExpireTime）")
    parser.add_argument(
        "--id-auth-expire-ms",
        type=int,
        help="设置认证过期时间：毫秒时间戳（由提示词先换算得到，再传给脚本）",
    )
    parser.add_argument("--id-auth-delete-user-id", help="清除用户认证信息：userId（internalAuthDeletePerson）")
    parser.add_argument(
        "--id-auth-fix-failure-user-id",
        help="解决认证失败：先查询该用户认证记录，提取最近一条 reason 中的账号列表，并逐个清除这些账号的认证记录",
    )

    parser.add_argument("--diamond-user-id", help="发放钻石：用户ID（provideDiamond）")
    parser.add_argument("--diamond-num", type=int, help="发放钻石：数量 num（正整数）")

    parser.add_argument("--package-gift-user-id", help="下发背包礼物：用户ID（addPackageGift）")
    parser.add_argument(
        "--package-gift-num",
        type=int,
        help="下发背包礼物：每种礼物的数量 productNum（默认取 config 中 giftDetails，通常为 100）",
    )
    parser.add_argument(
        "--package-gift-give-user-id",
        help="下发背包礼物：giveUserId（可选，默认空字符串）",
    )

    args = parser.parse_args()

    if not args.entry_url:
        print("缺少入口 URL：请传 --entry-url 或设置环境变量 MOA_ENTRY_URL", file=sys.stderr)
        return 2
    if not args.cookie:
        print("缺少 Cookie：请传 --cookie 或设置环境变量 MOA_COOKIE", file=sys.stderr)
        return 2

    try:
        # 可选请求头（不影响 payload），写入环境变量供 http 层读取
        if args.origin:
            os.environ["MOA_ORIGIN"] = args.origin
        if args.referer:
            os.environ["MOA_REFERER"] = args.referer
        if args.user_agent:
            os.environ["MOA_USER_AGENT"] = args.user_agent
        if args.request_source:
            os.environ["MOA_REQUEST_SOURCE"] = args.request_source

        # 认证失败自愈：query -> parse reason -> delete each userId in reason
        if args.id_auth_fix_failure_user_id is not None and args.expr is None:
            timeout_s = max(args.timeout_ms, 1) / 1000.0

            # 1) query reason list
            q_args = argparse.Namespace(**vars(args))
            q_args.id_auth_user_id = args.id_auth_fix_failure_user_id
            q_args.id_auth_output = "json"
            # 避免与其他实名相关参数冲突
            q_args.id_auth_delete_user_id = None
            q_args.id_auth_reset_expire_user_id = None
            q_args.diamond_user_id = None
            q_args.package_gift_user_id = None
            q_payload = _load_payload(q_args)
            q_resp = _http_post_json(args.entry_url, args.cookie, q_payload, timeout_s=timeout_s)
            q_ec, q_em, _ = _extract_ec_em_result(q_resp)
            if not _outer_success(q_ec):
                raise RuntimeError(f"查询认证记录失败(外层): ec={q_ec}, em={q_em}")
            inner_ec, inner_em, inner_result = _extract_inner_result(q_resp)
            if inner_ec != 0:
                raise RuntimeError(f"查询认证记录失败(业务): ec={inner_ec}, em={inner_em}")

            reason_user_ids = _extract_latest_id_auth_reason_list(inner_result)
            print(
                json.dumps(
                    {"userId": str(args.id_auth_fix_failure_user_id), "reasonUserIds": reason_user_ids},
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            if not reason_user_ids:
                # 没有需要清除的账号，直接输出空并结束
                print("[]")
                return 0

            # 2) delete each
            results: list[dict[str, Any]] = []
            for uid in reason_user_ids:
                d_args = argparse.Namespace(**vars(args))
                # 强制进入 delete 模式，清空其他实名相关参数，避免 _load_payload 命中其它分支
                d_args.id_auth_user_id = None
                d_args.id_auth_reset_expire_user_id = None
                d_args.id_auth_fix_failure_user_id = None
                d_args.diamond_user_id = None
                d_args.package_gift_user_id = None
                d_args.id_auth_delete_user_id = uid
                d_payload = _load_payload(d_args)
                d_resp = _http_post_json(args.entry_url, args.cookie, d_payload, timeout_s=timeout_s)
                d_ec, d_em, _ = _extract_ec_em_result(d_resp)
                ok_outer = _outer_success(d_ec)
                ok_inner = False
                inner_err = None
                try:
                    d_inner_ec, d_inner_em, _ = _extract_inner_result(d_resp)
                    ok_inner = d_inner_ec == 0
                    if not ok_inner:
                        inner_err = {"ec": d_inner_ec, "em": d_inner_em}
                except Exception as e:
                    inner_err = str(e)

                results.append(
                    {
                        "deletedUserId": uid,
                        "outer": {"ec": d_ec, "em": d_em, "ok": ok_outer},
                        "innerOk": ok_inner,
                        "innerErr": inner_err,
                    }
                )

            # 输出汇总（便于复制/留存）
            print(json.dumps({"fixedForUserId": str(args.id_auth_fix_failure_user_id), "deletions": results}, ensure_ascii=False, indent=2))
            return 0

        # VIP 目标等级升级：先 query，再补差值
        if args.vip_level is not None and args.vip_user_id is not None and args.vip_exp is None and not args.vip_query_current and args.expr is None:
            q_args = argparse.Namespace(**vars(args))
            q_args.vip_query_current = True
            q_payload = _load_payload(q_args)
            timeout_s = max(args.timeout_ms, 1) / 1000.0
            q_resp = _http_post_json(args.entry_url, args.cookie, q_payload, timeout_s=timeout_s)
            q_ec, q_em, _ = _extract_ec_em_result(q_resp)
            if not _outer_success(q_ec):
                raise RuntimeError(f"查询当前 VIP 经验值失败(外层): ec={q_ec}, em={q_em}")
            inner_ec, inner_em, inner_result = _extract_inner_result(q_resp)
            if inner_ec != 0:
                raise RuntimeError(f"查询当前 VIP 经验值失败(业务): ec={inner_ec}, em={inner_em}")
            current_vip_exp = _parse_current_exp_from_inner(inner_result)
            delta = _build_vip_exp_delta_for_level(args.vip_level, current_exp=current_vip_exp)
            print(f"已查询当前 VIP 经验值: {current_vip_exp}，目标 VIP 等级: {args.vip_level}，需要增加: {delta}", file=sys.stderr)

            e_args = argparse.Namespace(**vars(args))
            e_args.vip_current_exp = current_vip_exp
            e_args.vip_exp = delta
            e_args.vip_level = None
            payload = _load_payload(e_args)

        # 目标等级升级：先查询当前经验值，再补差值
        elif args.level is not None and args.room_id is not None and args.exp is None and not args.query_current and args.expr is None:
            # 1) query current exp via 0D
            q_args = argparse.Namespace(**vars(args))
            q_args.query_current = True
            q_args.exp = None
            q_payload = _load_payload(q_args)
            timeout_s = max(args.timeout_ms, 1) / 1000.0
            q_resp = _http_post_json(args.entry_url, args.cookie, q_payload, timeout_s=timeout_s)
            q_ec, q_em, _ = _extract_ec_em_result(q_resp)
            if not _outer_success(q_ec):
                raise RuntimeError(f"查询当前经验值失败(外层): ec={q_ec}, em={q_em}")
            inner_ec, inner_em, inner_result = _extract_inner_result(q_resp)
            if inner_ec != 0:
                raise RuntimeError(f"查询当前经验值失败(业务): ec={inner_ec}, em={inner_em}")
            current_exp = _parse_current_exp_from_inner(inner_result)
            delta = _build_room_exp_delta_for_level(args.level, current_exp=current_exp)
            print(f"已查询当前经验值: {current_exp}，目标等级: {args.level}，需要增加: {delta}", file=sys.stderr)

            # 2) execute add delta
            e_args = argparse.Namespace(**vars(args))
            e_args.current_exp = current_exp
            e_args.exp = None
            e_payload = _load_payload(e_args)
            payload = e_payload
        else:
            payload = _load_payload(args)

        # 仅输出非敏感的关键信息，便于排查（不打印 cookie）
        settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
        params0 = None
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
        if args.dump_payload:
            print("最终 payload（不含 cookie）:", file=sys.stderr)
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        timeout_s = max(args.timeout_ms, 1) / 1000.0
        resp = _http_post_json(args.entry_url, args.cookie, payload, timeout_s=timeout_s)
    except Exception as e:
        print(f"执行失败: {e}", file=sys.stderr)
        return 1

    # 实名认证：默认只输出最近一条 reason（你要求的交互）
    if args.id_auth_user_id is not None and args.id_auth_output == "latest-reason":
        try:
            inner_ec, inner_em, inner_result = _extract_inner_result(resp)
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 4
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            return 4
        if not isinstance(inner_result, dict):
            print("无法解析实名认证业务返回 result（不是 object）", file=sys.stderr)
            return 4
        latest = (inner_result.get("data") or {}).get("list") if isinstance(inner_result.get("data"), dict) else None
        if not isinstance(latest, list) or not latest:
            print("")
        else:
            reason = latest[0].get("reason")
            if isinstance(reason, (dict, list)):
                print(json.dumps(reason, ensure_ascii=False))
            else:
                print("" if reason is None else str(reason))
    else:
        print(json.dumps(resp, ensure_ascii=False, indent=2))

    ec, em, _ = _extract_ec_em_result(resp)
    if not _outer_success(ec):
        msg = em or "ec!=0"
        print(f"MOA 返回失败: ec={ec}, em={msg}", file=sys.stderr)
        return 3

    if args.query_current:
        try:
            inner_ec, inner_em, inner_result = _extract_inner_result(resp)
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 4
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            return 4
        try:
            current_exp = _parse_current_exp_from_inner(inner_result)
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 4
        lv = _level_by_exp(current_exp)
        thresholds = _room_level_thresholds()
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

    if args.vip_query_current:
        try:
            inner_ec, inner_em, inner_result = _extract_inner_result(resp)
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 4
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            return 4
        try:
            current_exp = _parse_current_exp_from_inner(inner_result)
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 4
        lv = _vip_level_by_exp(current_exp)
        thresholds = _vip_level_thresholds()
        next_lv = lv + 1 if (lv + 1) in thresholds else None
        next_threshold = thresholds.get(next_lv) if next_lv else None
        remaining = (next_threshold - current_exp) if next_threshold is not None else None
        print(
            json.dumps(
                {
                    "userId": args.vip_user_id,
                    "currentVipExp": current_exp,
                    "vipLevel": lv,
                    "nextVipLevelThreshold": next_threshold,
                    "remainingToNextVipLevel": remaining,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

