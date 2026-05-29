"""Yaahlan Admin HTTP 客户端。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def build_auth_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    sso_token = os.environ.get("ADMIN_SSO_TOKEN", "").strip()
    yaahlan_jwt = os.environ.get("ADMIN_YAAHLAN_JWT", "").strip()
    if not sso_token:
        raise ValueError("缺少 ADMIN_SSO_TOKEN（请写入 Admin/.env.local）")
    if not yaahlan_jwt:
        raise ValueError("缺少 ADMIN_YAAHLAN_JWT（请写入 Admin/.env.local）")

    headers["sso-token"] = sso_token
    headers["yaahlan-jwt"] = yaahlan_jwt
    headers["yaahlan-lang"] = os.environ.get("ADMIN_LANG", "zh").strip() or "zh"

    for env_key, header_key in (
        ("ADMIN_ORIGIN", "Origin"),
        ("ADMIN_REFERER", "Referer"),
        ("ADMIN_USER_AGENT", "User-Agent"),
    ):
        value = os.environ.get(env_key, "").strip()
        if value:
            headers[header_key] = value
    return headers


def http_post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req_headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        **build_auth_headers(),
    }

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


def admin_success(ec: Any) -> bool:
    try:
        return int(ec) == 200
    except (TypeError, ValueError):
        return False
