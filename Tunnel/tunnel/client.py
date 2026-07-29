"""Tunnel 抓包平台 HTTP 客户端。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def build_auth_headers() -> dict[str, str]:
    cookie = os.environ.get("TUNNEL_COOKIE", "").strip()
    if not cookie:
        raise ValueError(
            "缺少 TUNNEL_COOKIE（写入 Tunnel/.env.local，或复用 MOA/.env.local 的 MOA_COOKIE）"
        )

    headers: dict[str, str] = {
        "Accept": "application/json, text/plain, */*",
        "Cookie": cookie,
    }
    for env_key, header_key in (
        ("TUNNEL_REFERER", "Referer"),
        ("TUNNEL_ORIGIN", "Origin"),
        ("TUNNEL_USER_AGENT", "User-Agent"),
    ):
        value = os.environ.get(env_key, "").strip()
        if value:
            headers[header_key] = value
    return headers


def http_get_json(url: str, *, timeout_s: float = 15.0) -> dict[str, Any]:
    req = urllib.request.Request(
        url=url,
        method="GET",
        headers=build_auth_headers(),
    )
    return _read_json_response(req, timeout_s=timeout_s)


def _read_json_response(req: urllib.request.Request, *, timeout_s: float) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
        raise RuntimeError(f"HTTP {e.code}: {raw}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误: {e}") from e

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"返回不是合法 JSON: {raw[:1000]}") from e
    if not isinstance(obj, dict):
        raise RuntimeError("返回 JSON 不是 object")
    return obj


def tunnel_success(ec: Any) -> bool:
    try:
        code = int(ec)
    except (TypeError, ValueError):
        return False
    return code in (200, 201, 204)


def list_requests(
    *,
    base_url: str,
    momoid: str,
    start_time: int,
    keyword: str = "",
    g_appid: str = "All",
    g_env: str = "alpha",
    mode: str = "tunnel",
    timeout_s: float = 15.0,
) -> dict[str, Any]:
    params = {
        "momoid": momoid,
        "start_time": str(start_time),
        "mode": mode,
        "keyword": keyword,
        "g_appid": g_appid,
        "g_env": g_env,
    }
    url = f"{base_url.rstrip('/')}/api/requests?{urllib.parse.urlencode(params)}"
    return http_get_json(url, timeout_s=timeout_s)


def normalize_request_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    raw_list = data.get("list")
    if isinstance(raw_list, dict):
        return [item for item in raw_list.values() if isinstance(item, dict)]
    if isinstance(raw_list, list):
        return [item for item in raw_list if isinstance(item, dict)]
    return []
