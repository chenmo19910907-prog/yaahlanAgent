"""MDP Nova 道具后台 queryPropInfo 响应解析。"""

from __future__ import annotations

from typing import Any

from .gift import mdp_gift_success as mdp_prop_success


def _simplify_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "propId": row.get("propId"),
        "propName": row.get("propName"),
        "propTypeName": row.get("propTypeName"),
        "useType": row.get("useType"),
        "useTypeName": row.get("useTypeName"),
        "syncProdStatus": row.get("syncProdStatus"),
        "validStartTime": row.get("validStartTime"),
        "validEndTime": row.get("validEndTime"),
        "createTime": row.get("createTime"),
        "updateTime": row.get("updateTime"),
        "customized": row.get("customized"),
        "obtainWayEntryId": row.get("obtainWayEntryId"),
        "obtainWayEntryName": row.get("obtainWayEntryName"),
    }


def parse_query_prop_info_summary(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RuntimeError("无法解析道具列表 data（不是 object）")

    page_info = data.get("pageInfo")
    if not isinstance(page_info, dict):
        page_info = {}

    raw_records = data.get("records")
    if not isinstance(raw_records, list):
        raise RuntimeError("无法解析道具列表 records（不是 array）")

    records = [_simplify_record(row) for row in raw_records if isinstance(row, dict)]
    return {
        "pageNo": page_info.get("pageNo"),
        "pageSize": page_info.get("pageSize"),
        "totalCount": page_info.get("totalCount"),
        "totalPage": page_info.get("totalPage"),
        "returnedCount": len(records),
        "records": records,
    }
