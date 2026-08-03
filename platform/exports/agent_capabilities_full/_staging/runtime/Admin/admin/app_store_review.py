"""App Store 审核版本（get/update AppStoreReviewVersion）响应解析。"""

from __future__ import annotations

from typing import Any


def gateway_success(status: Any) -> bool:
    try:
        return int(status) == 0
    except (TypeError, ValueError):
        return False


def parse_app_store_review_version_summary(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RuntimeError("无法解析审核版本 data（不是 object）")

    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        raise RuntimeError("无法解析审核版本 items（不是 array）")

    items: list[dict[str, str]] = []
    for row in raw_items:
        if not isinstance(row, dict):
            continue
        ios_version = row.get("iosVersion")
        android_version_code = row.get("androidVersionCode")
        if ios_version is None and android_version_code is None:
            continue
        item: dict[str, str] = {}
        if ios_version is not None:
            item["iosVersion"] = str(ios_version)
        if android_version_code is not None:
            item["androidVersionCode"] = str(android_version_code)
        items.append(item)

    summary: dict[str, Any] = {
        "total": data.get("total"),
        "items": items,
    }
    if len(items) == 1:
        summary["iosVersion"] = items[0].get("iosVersion")
        summary["androidVersionCode"] = items[0].get("androidVersionCode")
    return summary


def parse_update_app_store_review_version_summary(
    resp: dict[str, Any],
    *,
    app_name: str,
    ios_version: str,
    android_version_code: str | None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "appName": app_name,
        "iosVersion": ios_version,
        "status": resp.get("status"),
        "msg": resp.get("msg"),
        "success": gateway_success(resp.get("status")),
        "data": resp.get("data"),
    }
    if android_version_code is not None:
        summary["androidVersionCode"] = android_version_code
    return summary
