"""用户详情与设备历史解析。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


_GENDER_MAP = {1: "男", 2: "女", 0: "未知"}


def _ms_to_iso(ms: Any) -> str | None:
    if ms in (None, "", 0):
        return None
    try:
        value = int(ms)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _pick(obj: Any, *keys: str) -> Any:
    if not isinstance(obj, dict):
        return None
    for key in keys:
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
    return None


def parse_user_detail_summary(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RuntimeError("无法解析用户详情 data（不是 object）")

    profile = data.get("userProfile") if isinstance(data.get("userProfile"), dict) else {}
    room = data.get("ownedRoomInfo") if isinstance(data.get("ownedRoomInfo"), dict) else {}
    anchor = data.get("anchorProfile") if isinstance(data.get("anchorProfile"), dict) else {}
    login_device = data.get("loginDeviceInfo") if isinstance(data.get("loginDeviceInfo"), dict) else {}
    register_device = data.get("registerDeviceInfo") if isinstance(data.get("registerDeviceInfo"), dict) else {}
    biz_status = data.get("bizFunctionStatus") if isinstance(data.get("bizFunctionStatus"), list) else []

    gender_raw = profile.get("gender")
    try:
        gender_label = _GENDER_MAP.get(int(gender_raw), str(gender_raw))
    except (TypeError, ValueError):
        gender_label = None

    area_code = _pick(profile, "areaCode")
    phone = _pick(profile, "phone")
    full_phone = f"+{area_code}{phone}" if area_code and phone else phone
    user_area = _pick(profile, "area") or _pick(anchor, "area")

    summary: dict[str, Any] = {
        "userId": _pick(profile, "userId"),
        "nickname": _pick(profile, "nickname"),
        "phone": phone,
        "areaCode": area_code,
        "area": user_area,
        "fullPhone": full_phone,
        "bindEmail": _pick(profile, "bindEmail", "mail"),
        "homeCountry": _pick(profile, "homeCountry"),
        "gender": gender_label,
        "age": profile.get("age"),
        "birthday": _ms_to_iso(profile.get("birthday")),
        "accountState": profile.get("state"),
        "regTypeName": _pick(profile, "regTypeName"),
        "regTime": _ms_to_iso(profile.get("regTime")),
        "onlineStatus": profile.get("onlineStatus"),
        "lastOnLineTime": _ms_to_iso(profile.get("lastOnLineTime")),
        "vipLevel": profile.get("vipLevel"),
        "nobleLevel": profile.get("nobleLevel"),
        "wealthLevel": profile.get("wealthLevel"),
        "charmLevel": profile.get("charmLevel"),
        "diamonds": data.get("diamonds"),
        "coinCount": data.get("coinCount"),
        "dealerAccountBalance": data.get("dealerAccountBalance"),
        "isDealer": data.get("isDealer"),
        "roomId": _pick(room, "roomId"),
        "roomName": _pick(room, "roomName"),
        "roomStatus": room.get("status"),
        "roomLevel": room.get("level"),
        "guildId": _pick(anchor, "tradeUnionId"),
        "guildName": _pick(anchor, "tradeUnionName"),
        "guildRole": _pick(anchor, "tradeRole"),
        "loginDevice": {
            "ip": _pick(login_device, "ip"),
            "ipCountry": _pick(login_device, "ipCountry"),
            "ua": _pick(login_device, "ua"),
            "mmuid": _pick(login_device, "mmuid", "uuid"),
            "mmuidv3": _pick(login_device, "mmuidv3"),
            "loginTime": _ms_to_iso(login_device.get("loginTime")),
        },
        "registerDevice": {
            "ip": _pick(register_device, "ip"),
            "ipCountry": _pick(register_device, "ipCountry"),
            "ua": _pick(register_device, "ua"),
            "mmuid": _pick(register_device, "mmuid", "uuid"),
            "mmuidv3": _pick(register_device, "mmuidv3"),
            "loginTime": _ms_to_iso(register_device.get("loginTime")),
        },
        "bizFunctionStatus": [
            {
                "functionName": item.get("functionName"),
                "statusName": item.get("statusName"),
                "expireTime": _ms_to_iso(item.get("expireTime")),
            }
            for item in biz_status
            if isinstance(item, dict)
        ],
    }
    return summary


def _normalize_history_device_row(row: dict[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = {}
    for key in (
        "mmuidv3",
        "mmuid",
        "ip",
        "ipCountry",
        "ua",
        "count",
        "anchorCount",
        "userCount",
        "multiTradeUnion",
    ):
        value = row.get(key)
        if value is not None:
            item[key] = value
    create_time = _ms_to_iso(row.get("createTime"))
    if create_time:
        item["createTime"] = create_time
    return item


def parse_user_history_device_summary(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RuntimeError("无法解析历史设备 data（不是 object）")
    raw_list = data.get("list")
    if not isinstance(raw_list, list):
        raise RuntimeError("无法解析历史设备 list（不是 array）")

    items = [_normalize_history_device_row(row) for row in raw_list if isinstance(row, dict)]
    return {
        "total": data.get("total"),
        "returnedCount": len(items),
        "items": items,
    }


def _anchor_label(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return "是" if int(value) == 1 else "否"
    except (TypeError, ValueError):
        return str(value)


def _normalize_history_user_by_device_row(row: dict[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = {}
    for key in (
        "userId",
        "nickName",
        "vipLevel",
        "tradeUnionName",
        "lastPeriodSalary",
    ):
        value = row.get(key)
        if value is not None:
            item[key] = value

    is_anchor = _anchor_label(row.get("isAnchor"))
    if is_anchor is not None:
        item["isAnchor"] = is_anchor

    for time_key in ("createTime", "updateTime", "anchorCreateTime"):
        iso_time = _ms_to_iso(row.get(time_key))
        if iso_time:
            item[time_key] = iso_time
    return item


def parse_history_user_list_by_device_summary(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RuntimeError("无法解析设备历史账号 data（不是 object）")
    raw_list = data.get("list")
    if not isinstance(raw_list, list):
        raise RuntimeError("无法解析设备历史账号 list（不是 array）")

    items = [_normalize_history_user_by_device_row(row) for row in raw_list if isinstance(row, dict)]
    return {
        "total": data.get("total"),
        "returnedCount": len(items),
        "items": items,
    }
