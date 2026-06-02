"""VIP5 定制礼物列表（userId ↔ giftId）解析。"""

from __future__ import annotations

from typing import Any


def gateway_success(status: Any) -> bool:
    try:
        return int(status) == 0
    except (TypeError, ValueError):
        return False


def _normalize_items(data: Any) -> list[dict[str, str]]:
    if not isinstance(data, dict):
        raise RuntimeError("无法解析定制礼物列表 data（不是 object）")
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        raise RuntimeError("无法解析定制礼物列表 items（不是 array）")

    items: list[dict[str, str]] = []
    for row in raw_items:
        if not isinstance(row, dict):
            continue
        gift_id = row.get("giftId")
        user_id = row.get("userId")
        if gift_id is None or user_id is None:
            continue
        items.append({"giftId": str(gift_id), "userId": str(user_id)})
    return items


def parse_custom_gift_list_summary(data: Any, *, filter_user_id: str | None = None) -> dict[str, Any]:
    items = _normalize_items(data)
    total = data.get("total") if isinstance(data, dict) else None

    if filter_user_id is not None:
        target = str(filter_user_id).strip()
        matched = [item for item in items if item["userId"] == target]
        return {
            "total": total,
            "filterUserId": target,
            "matchedCount": len(matched),
            "items": matched,
        }

    return {
        "total": total,
        "returnedCount": len(items),
        "items": items,
    }
