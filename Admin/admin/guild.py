"""公会（anchor）后台接口响应解析。"""

from __future__ import annotations

from typing import Any


def anchor_success(resp: dict[str, Any]) -> bool:
    if resp.get("success") is True:
        return True
    try:
        return int(resp.get("ec")) == 200
    except (TypeError, ValueError):
        return False


def parse_add_guild_member_summary(
    resp: dict[str, Any],
    *,
    trade_id: str,
    trade_union: str,
    user_ids: str,
) -> dict[str, Any]:
    return {
        "tradeId": trade_id or None,
        "tradeUnion": trade_union or None,
        "userIds": user_ids,
        "ec": resp.get("ec"),
        "em": resp.get("em"),
        "data": resp.get("data"),
        "success": anchor_success(resp),
    }


def parse_anchor_id_list(raw: str) -> list[str]:
    items = [part.strip() for part in raw.split(",") if part.strip()]
    if not items:
        raise ValueError("用户 ID 列表不能为空")
    return items


def parse_remove_guild_member_summary(
    resp: dict[str, Any],
    *,
    anchor_id_list: list[str],
) -> dict[str, Any]:
    return {
        "anchorIdList": anchor_id_list,
        "ec": resp.get("ec"),
        "em": resp.get("em"),
        "data": resp.get("data"),
        "success": anchor_success(resp),
    }


def parse_change_guild_member_summary(
    resp: dict[str, Any],
    *,
    trade_union: str,
    user_id_set: list[str],
) -> dict[str, Any]:
    return {
        "tradeUnion": trade_union,
        "userIdSet": user_id_set,
        "ec": resp.get("ec"),
        "em": resp.get("em"),
        "data": resp.get("data"),
        "success": anchor_success(resp),
    }


_PAYMENT_TYPE_LABELS: dict[int, str] = {
    0: "待分配",
    1: "公会收",
    2: "主播收",
}


def _normalize_trade_union_row(row: dict[str, Any], *, is_child: bool = False) -> dict[str, Any]:
    payment_type = row.get("paymentType")
    try:
        payment_type_int = int(payment_type)
    except (TypeError, ValueError):
        payment_type_int = None

    item: dict[str, Any] = {
        "tradeId": row.get("tid"),
        "tradeUnion": row.get("tradeUnion"),
        "tradeUid": row.get("tradeUid"),
        "anchorNum": row.get("anchorNum"),
        "activeAnchorNum": row.get("activeAnchorNum"),
        "paymentType": payment_type_int,
        "paymentTypeLabel": _PAYMENT_TYPE_LABELS.get(payment_type_int) if payment_type_int is not None else None,
        "startDate": row.get("startDate"),
        "optName": row.get("optName"),
        "area": row.get("area"),
    }
    if is_child:
        item["subTradeShareRadio"] = row.get("subTradeShareRadio")
        item["superTradeId"] = row.get("superTradeId") or None
    else:
        child_list = row.get("childList")
        if isinstance(child_list, list):
            item["childUnions"] = [
                _normalize_trade_union_row(child, is_child=True)
                for child in child_list
                if isinstance(child, dict)
            ]
            item["childCount"] = len(item["childUnions"])
    return item


def parse_query_trade_union_summary(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RuntimeError("无法解析公会查询 data（不是 object）")
    raw_list = data.get("list")
    if not isinstance(raw_list, list):
        raise RuntimeError("无法解析公会查询 list（不是 array）")

    items = [_normalize_trade_union_row(row) for row in raw_list if isinstance(row, dict)]
    return {
        "totalCount": data.get("totalCount"),
        "realTotalTradeCount": data.get("realTotalTradeCount"),
        "returnedCount": len(items),
        "items": items,
    }
