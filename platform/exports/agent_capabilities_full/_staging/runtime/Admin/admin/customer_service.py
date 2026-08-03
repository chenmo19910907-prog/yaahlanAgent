"""客服账号后台接口响应解析。"""

from __future__ import annotations

from typing import Any


_ENABLE_LABELS: dict[int, str] = {
    0: "禁用",
    1: "启用",
}

_TAKING_ORDER_LABELS: dict[int, str] = {
    0: "未接单",
    1: "接单中",
}

ROLE_LABELS: dict[int, str] = {
    1: "VIP客服",
    2: "游戏客服",
    3: "语音房客服",
    4: "Admin客服",
    5: "公会通知审核客服",
    6: "公会运营客服",
}

_OPT_TYPE_LABELS: dict[int, str] = {
    1: "创建",
    2: "编辑",
}


def parse_cs_role_list(raw: str) -> list[int]:
    items: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            role = int(part)
        except ValueError as e:
            raise ValueError(f"无效的客服角色 ID: {part}") from e
        if role not in ROLE_LABELS:
            raise ValueError(f"未知的客服角色 ID: {role}")
        items.append(role)
    if not items:
        raise ValueError("客服角色列表不能为空")
    return items


def _role_labels(role_list: list[int]) -> list[str]:
    return [ROLE_LABELS[role] for role in role_list if role in ROLE_LABELS]


def _normalize_cs_row(row: dict[str, Any]) -> dict[str, Any]:
    enable = row.get("enable")
    try:
        enable_int = int(enable)
    except (TypeError, ValueError):
        enable_int = None

    taking_order = row.get("takingOrder")
    try:
        taking_order_int = int(taking_order)
    except (TypeError, ValueError):
        taking_order_int = None

    role_list = row.get("roleList")
    if not isinstance(role_list, list):
        role_list = None

    item: dict[str, Any] = {
        "userId": row.get("userId"),
        "area": row.get("area"),
        "nickname": row.get("nickname"),
        "avatar": row.get("avatar"),
        "takingOrder": taking_order_int,
        "takingOrderLabel": _TAKING_ORDER_LABELS.get(taking_order_int)
        if taking_order_int is not None
        else None,
        "roleList": role_list,
        "orderNumToday": row.get("orderNumToday"),
        "enable": enable_int,
        "enableLabel": _ENABLE_LABELS.get(enable_int) if enable_int is not None else None,
        "updateTime": row.get("updateTime"),
        "optUser": row.get("optUser"),
    }
    return item


def parse_query_cs_data_summary(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RuntimeError("无法解析客服查询 data（不是 object）")
    raw_list = data.get("list")
    if not isinstance(raw_list, list):
        raise RuntimeError("无法解析客服查询 list（不是 array）")

    items = [_normalize_cs_row(row) for row in raw_list if isinstance(row, dict)]
    return {
        "total": data.get("total"),
        "returnedCount": len(items),
        "items": items,
    }


def parse_save_cs_data_summary(
    resp: dict[str, Any],
    *,
    user_id: str,
    role_list: list[int],
    enable: int,
    taking_order: int,
    opt_type: int,
) -> dict[str, Any]:
    try:
        success = int(resp.get("ec")) == 200
    except (TypeError, ValueError):
        success = False

    return {
        "userId": user_id,
        "roleList": role_list,
        "roleLabels": _role_labels(role_list),
        "enable": enable,
        "enableLabel": _ENABLE_LABELS.get(enable),
        "takingOrder": taking_order,
        "takingOrderLabel": _TAKING_ORDER_LABELS.get(taking_order),
        "optType": opt_type,
        "optTypeLabel": _OPT_TYPE_LABELS.get(opt_type),
        "ec": resp.get("ec"),
        "em": resp.get("em"),
        "data": resp.get("data"),
        "success": success,
    }


def parse_change_cs_taking_order_summary(
    resp: dict[str, Any],
    *,
    user_id: str,
    taking_order: int,
) -> dict[str, Any]:
    try:
        success = int(resp.get("ec")) == 200
    except (TypeError, ValueError):
        success = False

    return {
        "userId": user_id,
        "takingOrder": taking_order,
        "takingOrderLabel": _TAKING_ORDER_LABELS.get(taking_order),
        "ec": resp.get("ec"),
        "em": resp.get("em"),
        "data": resp.get("data"),
        "success": success,
    }
