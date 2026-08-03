"""HTTP 客户端。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def http_post_json(
    url: str,
    payload: dict[str, Any],
    *,
    cookie: str | None = None,
    headers: dict[str, str] | None = None,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req_headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
    }
    if cookie:
        req_headers["Cookie"] = cookie
    if headers:
        req_headers.update(headers)

    for env_key, header_key in (
        ("SEC_RISK_ORIGIN", "Origin"),
        ("SEC_RISK_REFERER", "Referer"),
        ("SEC_RISK_USER_AGENT", "User-Agent"),
    ):
        value = os.environ.get(env_key)
        if value:
            req_headers[header_key] = value

    req = urllib.request.Request(url=url, data=body, method="POST", headers=req_headers)
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
