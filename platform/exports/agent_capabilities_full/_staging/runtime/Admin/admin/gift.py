"""MDP Nova 礼物后台 queryGiftList 响应解析。"""

from __future__ import annotations

from typing import Any


def mdp_gift_success(ec: Any) -> bool:
    try:
        return int(ec) == 200
    except (TypeError, ValueError):
        return False


def _simplify_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "baseId": row.get("baseId"),
        "productName": row.get("productName"),
        "price": row.get("price"),
        "nominalPrice": row.get("nominalPrice"),
        "giftType": row.get("giftType"),
        "giftSubType": row.get("giftSubType"),
        "giftEffectCate": row.get("giftEffectCate"),
        "giftStatus": row.get("giftStatus"),
        "createSource": row.get("createSource"),
        "createTime": row.get("createTime"),
        "cartoonEffectType": row.get("cartoonEffectType"),
    }


def parse_query_gift_list_summary(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RuntimeError("无法解析礼物列表 data（不是 object）")

    page_info = data.get("pageInfo")
    if not isinstance(page_info, dict):
        page_info = {}

    raw_records = data.get("records")
    if not isinstance(raw_records, list):
        raise RuntimeError("无法解析礼物列表 records（不是 array）")

    records = [_simplify_record(row) for row in raw_records if isinstance(row, dict)]
    return {
        "pageNo": page_info.get("pageNo"),
        "pageSize": page_info.get("pageSize"),
        "totalCount": page_info.get("totalCount"),
        "totalPage": page_info.get("totalPage"),
        "returnedCount": len(records),
        "records": records,
    }
