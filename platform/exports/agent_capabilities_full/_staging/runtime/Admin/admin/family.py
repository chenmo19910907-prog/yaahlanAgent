"""家族后台接口响应解析。"""

from __future__ import annotations

from typing import Any

from .custom_gift import gateway_success

_FAMILY_FIELD_MAP: tuple[tuple[str, str], ...] = (
    ("familyIcon", "familyIcon"),
    ("familyName", "familyName"),
    ("familyLevel", "familyLevel"),
    ("familyId", "familyId"),
    ("familyOwnerId", "familyOwnerId"),
    ("familyCreateDate", "familyCreateDate"),
    ("familyMemberNum", "familyMemberNum"),
    ("familyMemberActiveNum", "familyMemberActiveNum"),
    ("familyJoinMemberNum", "familyJoinMemberNum"),
    ("familyQuitMemberNum", "familyQuitMemberNum"),
)


def _normalize_family_row(row: dict[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = {}
    for key, source_key in _FAMILY_FIELD_MAP:
        value = row.get(source_key)
        if value is not None:
            item[key] = value
    return item


def parse_add_family_member_summary(
    resp: dict[str, Any],
    *,
    family_id: str,
    user_id: str,
) -> dict[str, Any]:
    return {
        "familyId": family_id,
        "userId": user_id,
        "status": resp.get("status"),
        "msg": resp.get("msg"),
        "data": resp.get("data"),
        "success": gateway_success(resp.get("status")),
    }


def parse_query_family_summary(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RuntimeError("无法解析家族查询 data（不是 object）")
    raw_list = data.get("list")
    if not isinstance(raw_list, list):
        raise RuntimeError("无法解析家族查询 list（不是 array）")

    items = [_normalize_family_row(row) for row in raw_list if isinstance(row, dict)]
    return {
        "total": data.get("cnt"),
        "returnedCount": len(items),
        "items": items,
    }
