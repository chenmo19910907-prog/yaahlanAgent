"""开发者后台用户关系（好友/关注/粉丝/拉黑）查询。"""

from __future__ import annotations

from typing import Any

from .client import admin_success, http_post_json

_RELATION_ALIASES: dict[str, str] = {
    "follow": "attention",
    "关注": "attention",
    "好友": "friend",
    "friend": "friend",
    "attention": "attention",
    "粉丝": "fans",
    "fans": "fans",
    "拉黑": "block",
    "block": "block",
}


def normalize_relation_type(raw: str) -> str:
    key = str(raw or "").strip().lower()
    if not key:
        raise ValueError("必须提供 --user-relation-type（friend / attention / fans / block）")
    mapped = _RELATION_ALIASES.get(key) or _RELATION_ALIASES.get(str(raw).strip())
    if not mapped:
        raise ValueError(
            f"不支持的 relationType: {raw!r}（可用: friend, attention, fans, block；关注可写 follow）"
        )
    return mapped


def parse_relation_summary_data(data: Any) -> dict[str, object]:
    if not isinstance(data, dict):
        return {
            "friendCount": None,
            "attentionCount": None,
            "fansCount": None,
            "blockCount": None,
        }
    return {
        "friendCount": data.get("friendCount"),
        "attentionCount": data.get("attentionCount"),
        "fansCount": data.get("fansCount"),
        "blockCount": data.get("blockCount"),
    }


def _parse_list_items(data: Any) -> list[dict[str, object]]:
    if not isinstance(data, dict):
        return []
    out: list[dict[str, object]] = []
    for row in data.get("list") or []:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "userId": row.get("userId"),
                "nickname": row.get("nickname"),
                "relationTime": row.get("relationTime"),
            }
        )
    return out


def parse_relation_list_page(
    data: Any,
    *,
    user_id: str,
    relation_type: str,
) -> dict[str, object]:
    if not isinstance(data, dict):
        data = {}
    return {
        "userId": user_id,
        "relationType": relation_type,
        "items": _parse_list_items(data),
        "index": data.get("index"),
        "hasMore": data.get("hasMore"),
        "totalDataCount": data.get("totalDataCount"),
    }


def _relation_paths(*, online: bool) -> tuple[str, str]:
    from .config import defaults

    list_cfg = defaults("query_user_relation_list", online=online)
    summary_cfg = defaults("query_user_relation_summary", online=online)
    list_path = str(list_cfg.get("path", "/admin/user/queryUserRelationList"))
    summary_path = str(summary_cfg.get("path", "/admin/user/queryUserRelationSummary"))
    return list_path, summary_path


def query_user_relation_summary(
    *,
    base_url: str,
    auth: str,
    user_id: str,
    timeout_s: float,
    online: bool = False,
) -> dict[str, object]:
    _, summary_path = _relation_paths(online=online)
    url = f"{base_url.rstrip('/')}{summary_path}"
    resp = http_post_json(url, {"userId": user_id}, timeout_s=timeout_s, auth=auth)
    if not admin_success(resp.get("ec")):
        raise RuntimeError(f"queryUserRelationSummary 失败: ec={resp.get('ec')}, em={resp.get('em')}")
    summary = parse_relation_summary_data(resp.get("data"))
    summary["userId"] = user_id
    return summary


def _list_request_body(user_id: str, relation_type: str, *, index: int, page_size: int) -> dict[str, object]:
    return {
        "userId": user_id,
        "relationType": relation_type,
        "index": index,
        "pageSize": page_size,
    }


def query_user_relation_list_page(
    *,
    base_url: str,
    auth: str,
    user_id: str,
    relation_type: str,
    index: int,
    page_size: int,
    timeout_s: float,
    online: bool = False,
) -> dict[str, object]:
    list_path, _ = _relation_paths(online=online)
    url = f"{base_url.rstrip('/')}{list_path}"
    body = _list_request_body(user_id, relation_type, index=index, page_size=page_size)
    resp = http_post_json(url, body, timeout_s=timeout_s, auth=auth)
    if not admin_success(resp.get("ec")):
        raise RuntimeError(f"queryUserRelationList 失败: ec={resp.get('ec')}, em={resp.get('em')}")
    return parse_relation_list_page(resp.get("data"), user_id=user_id, relation_type=relation_type)


def fetch_user_relation_list_all(
    *,
    base_url: str,
    auth: str,
    user_id: str,
    relation_type: str,
    page_size: int,
    timeout_s: float,
    online: bool = False,
) -> dict[str, object]:
    items: list[dict[str, object]] = []
    index = 0
    total: Any = None
    pages = 0
    while pages < 500:
        page = query_user_relation_list_page(
            base_url=base_url,
            auth=auth,
            user_id=user_id,
            relation_type=relation_type,
            index=index,
            page_size=page_size,
            timeout_s=timeout_s,
            online=online,
        )
        batch = page.get("items") or []
        if not isinstance(batch, list):
            batch = []
        items.extend(batch)
        total = page.get("totalDataCount", total)
        pages += 1
        if not page.get("hasMore"):
            break
        next_index = page.get("index")
        if isinstance(next_index, int) and next_index > index:
            index = next_index
        else:
            index += len(batch)
        if not batch:
            break
    return {
        "userId": user_id,
        "relationType": relation_type,
        "totalDataCount": total,
        "itemCount": len(items),
        "items": items,
        "pagesFetched": pages,
    }
