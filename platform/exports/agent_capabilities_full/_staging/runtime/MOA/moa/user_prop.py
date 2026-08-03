"""用户装扮道具 MOA 响应解析。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROP_TYPES_PATH = Path(__file__).resolve().parent.parent / "config" / "prop_types.json"


def load_prop_type_labels() -> dict[str, str]:
    if not _PROP_TYPES_PATH.is_file():
        return {}
    data = json.loads(_PROP_TYPES_PATH.read_text(encoding="utf-8"))
    types = data.get("types")
    return {str(k): str(v) for k, v in types.items()} if isinstance(types, dict) else {}


def _iter_prop_items(inner_result: Any) -> list[dict[str, Any]]:
    if inner_result is None:
        return []
    if isinstance(inner_result, list):
        return [item for item in inner_result if isinstance(item, dict)]
    if isinstance(inner_result, dict):
        for key in ("list", "propList", "props", "data", "items"):
            val = inner_result.get(key)
            if isinstance(val, list):
                return [item for item in val if isinstance(item, dict)]
        if any(k in inner_result for k in ("propId", "propName", "propTypeCode")):
            return [inner_result]
    return []


def format_prop_expire(item: dict[str, Any]) -> str:
    validity = item.get("validityPeriod")
    if validity == -1:
        return "永久"
    end_ms = item.get("propUseEndTime") or item.get("expireTime") or item.get("expireAt")
    if end_ms in (None, "", 0):
        return "—"
    try:
        end_ms_int = int(end_ms)
    except (TypeError, ValueError):
        return str(end_ms)
    # 远端占位时间戳视为永久
    if end_ms_int >= 7258089599000:
        return "永久"
    dt = datetime.fromtimestamp(end_ms_int / 1000, tz=timezone.utc).astimezone()
    return dt.strftime("%Y-%m-%d %H:%M:%S %z")


def parse_user_prop_summary(
    user_id: str,
    prop_type_code: str,
    inner_result: Any,
) -> dict[str, Any]:
    labels = load_prop_type_labels()
    items = _iter_prop_items(inner_result)
    simplified: list[dict[str, Any]] = []
    for item in items:
        simplified.append(
            {
                "propId": item.get("propId") or item.get("id") or item.get("productId"),
                "propName": item.get("propName") or item.get("name") or item.get("title"),
                "expireTime": format_prop_expire(item),
                "propUseEndTime": item.get("propUseEndTime"),
                "validityPeriod": item.get("validityPeriod"),
                "wearStatus": item.get("wearState") if item.get("wearState") is not None else item.get("wearStatus"),
                "count": item.get("count") or item.get("num"),
            }
        )
    return {
        "userId": str(user_id),
        "propTypeCode": str(prop_type_code),
        "propTypeName": labels.get(str(prop_type_code), ""),
        "count": len(items),
        "items": simplified,
    }
