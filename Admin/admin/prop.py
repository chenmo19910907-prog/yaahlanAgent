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


def build_query_prop_info_body(
    *,
    prop_id: str = "",
    prop_name: str = "",
    prop_type_code: str = "",
    obtain_way_entry_id: str = "",
    sync_prod_status: str = "",
    identifier: str | None = None,
    app_id: int = 2005,
    page_no: int = 1,
    page_size: int = 20,
) -> dict[str, object]:
    """构造 propAdmin/queryPropInfo 请求体（与 MDP Nova 后台一致）。"""
    ident = identifier
    if ident is not None and str(ident).strip() == "":
        ident = None
    return {
        "appId": app_id,
        "propTypeCode": str(prop_type_code or "").strip(),
        "propName": str(prop_name or "").strip(),
        "propId": str(prop_id or "").strip(),
        "obtainWayEntryId": str(obtain_way_entry_id or "").strip(),
        "syncProdStatus": str(sync_prod_status or "").strip(),
        "identifier": ident,
        "pageNo": page_no,
        "pageSize": page_size,
    }


def fetch_prop_info_by_id(
    prop_id: str,
    *,
    app_id: int = 2005,
    page_size: int = 20,
) -> dict[str, Any] | None:
    """按 propId 精确查询单条道具配置；失败或未找到返回 None。"""
    from .client import http_post_json
    from .config import defaults

    pid = str(prop_id or "").strip()
    if not pid:
        return None
    cfg = defaults("query_prop_info")
    base_url = str(
        cfg.get("baseUrl") or "https://alpha-mdp-user-admin-api-stage.wemomo.com"
    ).rstrip("/")
    path = str(cfg.get("path") or "/propAdmin/queryPropInfo")
    if app_id == 2005:
        try:
            app_id = int(cfg.get("defaultAppId") or 2005)
        except (TypeError, ValueError):
            app_id = 2005
    body = build_query_prop_info_body(
        prop_id=pid,
        app_id=app_id,
        page_no=1,
        page_size=page_size,
    )
    resp = http_post_json(f"{base_url}{path}", body, auth="mdp_nova")
    if not mdp_prop_success(resp.get("ec")):
        return None
    summary = parse_query_prop_info_summary(resp.get("data"))
    records = summary.get("records") or []
    if not records:
        return None
    first = records[0]
    return first if isinstance(first, dict) else None


def lookup_prop_names(prop_ids: list[str]) -> dict[str, dict[str, Any]]:
    """批量按 propId 查道具名；查不到则跳过，不阻断调用方。"""
    out: dict[str, dict[str, Any]] = {}
    for raw in prop_ids:
        pid = str(raw or "").strip()
        if not pid or pid in out:
            continue
        try:
            info = fetch_prop_info_by_id(pid)
        except Exception:
            continue
        if info:
            out[pid] = info
    return out
