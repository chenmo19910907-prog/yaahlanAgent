"""Tunnel 响应摘要格式化。"""

from __future__ import annotations

import json
from typing import Any


def _short_url(url: str, *, max_len: int = 72) -> str:
    if len(url) <= max_len:
        return url
    return url[: max_len - 3] + "..."


def format_list_summary(
    items: list[dict[str, Any]],
    *,
    limit: int = 30,
) -> str:
    if not items:
        return "（无匹配请求）"

    sorted_items = sorted(
        items,
        key=lambda x: str(x.get("time", "")),
        reverse=True,
    )
    shown = sorted_items[:limit]
    lines = [
        f"共 {len(items)} 条，展示最近 {len(shown)} 条：",
        "",
        "| 时间 | 方法 | 状态 | 耗时ms | URL |",
        "|------|------|------|--------|-----|",
    ]
    for item in shown:
        lines.append(
            "| {time} | {method} | {status} | {cost} | {url} |".format(
                time=str(item.get("time", "")),
                method=str(item.get("method", "")),
                status=str(item.get("status", "")),
                cost=str(item.get("time_cost", "")),
                url=_short_url(str(item.get("url", ""))),
            )
        )
    if len(items) > limit:
        lines.append("")
        lines.append(f"（另有 {len(items) - limit} 条未展示，可用 --limit 或 --output json 查看）")
    return "\n".join(lines)


def format_request_detail(item: dict[str, Any]) -> str:
    lines = [
        f"_id: {item.get('_id', '')}",
        f"time: {item.get('time', '')}",
        f"method: {item.get('method', '')}  status: {item.get('status', '')}  cost: {item.get('time_cost', '')}ms",
        f"url: {item.get('url', '')}",
        f"appId: {item.get('appId', '')}  env: {item.get('env', '')}  momoid: {item.get('momoid', '')}",
        "",
        "request:",
        json.dumps(item.get("request"), ensure_ascii=False, indent=2),
        "",
        "response:",
        json.dumps(item.get("response"), ensure_ascii=False, indent=2),
    ]
    return "\n".join(lines)
