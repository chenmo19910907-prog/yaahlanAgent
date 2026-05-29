"""用户详情解析。"""

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

    summary: dict[str, Any] = {
        "userId": _pick(profile, "userId"),
        "nickname": _pick(profile, "nickname"),
        "phone": phone,
        "areaCode": area_code,
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
