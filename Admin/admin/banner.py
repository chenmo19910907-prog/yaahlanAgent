"""Banner 配置（cms/backend/banner/getBannerList）。"""

from __future__ import annotations

from typing import Any

from .client import http_post_json
from .config import defaults
from .custom_gift import gateway_success

# 后台 banner 类型（抓包 + 用例归纳；未列出的仍返回原始 type）
BANNER_TYPE_LABELS: dict[int, str] = {
    1: "房间",
    2: "钱包",
    3: "礼物面板",
    4: "Game 页",
    5: "活动",
    6: "消息列表",
    7: "搜索推荐",
    8: "聚合页",
}

# status=-1 表示全部；其余以抓包/后台为准
BANNER_STATUS_LABELS: dict[int, str] = {
    -1: "全部",
    0: "下线",
    1: "上线",
}


def build_get_banner_list_body(
    *,
    area: str = "MENA",
    banner_type: int = 5,
    status: int = -1,
    page: int = 1,
    per_page: int = 10,
    banner_id: str = "",
) -> dict[str, Any]:
    return {
        "bannerId": str(banner_id or "").strip(),
        "page": int(page),
        "perPage": int(per_page),
        "status": int(status),
        "type": int(banner_type),
        "area": str(area or "MENA").strip() or "MENA",
    }


def _normalize_banner_row(row: dict[str, Any]) -> dict[str, Any]:
    banner_type = row.get("type")
    try:
        banner_type_int = int(banner_type)
    except (TypeError, ValueError):
        banner_type_int = None

    banner_status = row.get("status")
    try:
        banner_status_int = int(banner_status)
    except (TypeError, ValueError):
        banner_status_int = banner_status

    return {
        "id": row.get("id") or row.get("bannerId"),
        "name": row.get("name") or row.get("bannerName"),
        "type": banner_type_int,
        "typeLabel": BANNER_TYPE_LABELS.get(banner_type_int) if banner_type_int is not None else None,
        "status": banner_status_int,
        "statusLabel": BANNER_STATUS_LABELS.get(banner_status_int)
        if isinstance(banner_status_int, int)
        else None,
        "area": row.get("area"),
        "startTime": row.get("startTime"),
        "endTime": row.get("endTime"),
        "jumpType": row.get("jumpType"),
        "jumpUrl": row.get("jumpUrl") or row.get("url") or row.get("gotoStr"),
        "sort": row.get("sort"),
    }


def _extract_banner_rows(data: Any) -> tuple[list[dict[str, Any]], int | None]:
    total: int | None = None
    rows: list[Any]

    if isinstance(data, dict):
        total_raw = data.get("total") or data.get("totalCount") or data.get("count")
        try:
            total = int(total_raw) if total_raw is not None else None
        except (TypeError, ValueError):
            total = None
        list_raw = (
            data.get("items")
            or data.get("list")
            or data.get("bannerList")
            or data.get("records")
            or data.get("rows")
            or data.get("data")
        )
        rows = list_raw if isinstance(list_raw, list) else []
    elif isinstance(data, list):
        rows = data
    else:
        rows = []

    banners = [_normalize_banner_row(row) for row in rows if isinstance(row, dict)]
    return banners, total


def parse_query_banner_list_summary(
    data: Any,
    *,
    area: str | None = None,
    banner_type: int | None = None,
    status: int | None = None,
    page: int | None = None,
    per_page: int | None = None,
    banner_id: str | None = None,
    name_contains: str | None = None,
) -> dict[str, Any]:
    banners, total = _extract_banner_rows(data)

    if name_contains:
        needle = str(name_contains).strip().lower()
        banners = [
            banner
            for banner in banners
            if needle in str(banner.get("name") or "").strip().lower()
        ]

    if banner_id:
        needle_id = str(banner_id).strip()
        banners = [
            banner
            for banner in banners
            if str(banner.get("id") or "").strip() == needle_id
        ]

    return {
        "area": area,
        "type": banner_type,
        "typeLabel": BANNER_TYPE_LABELS.get(banner_type) if banner_type is not None else None,
        "status": status,
        "statusLabel": BANNER_STATUS_LABELS.get(status) if isinstance(status, int) else None,
        "page": page,
        "perPage": per_page,
        "bannerIdFilter": str(banner_id).strip() if banner_id else None,
        "nameContainsFilter": str(name_contains).strip() if name_contains else None,
        "total": total,
        "returnedCount": len(banners),
        "banners": banners,
    }


def fetch_banner_list(
    *,
    area: str = "MENA",
    banner_type: int = 5,
    status: int = -1,
    page: int = 1,
    per_page: int = 10,
    banner_id: str = "",
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    cfg = defaults("query_banner_list")
    base_url = str(cfg.get("baseUrl") or "https://melon-gateway-alpha-stage.immomo.com").rstrip("/")
    path = str(cfg.get("path") or "/yaahlan/cms/backend/banner/getBannerList")
    body = build_get_banner_list_body(
        area=area,
        banner_type=banner_type,
        status=status,
        page=page,
        per_page=per_page,
        banner_id=banner_id,
    )
    resp = http_post_json(f"{base_url}{path}", body, timeout_s=timeout_s)
    if not gateway_success(resp.get("status")):
        raise RuntimeError(f"getBannerList 失败: status={resp.get('status')}, msg={resp.get('msg')}")
    return resp
