"""MSE 配置中心 HTTP 客户端。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _headers(cookie: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json, text/plain, */*",
        "Cookie": cookie,
        "request-source": os.environ.get("MSE_REQUEST_SOURCE", "config"),
    }
    for env_key, header_key in (
        ("MSE_ORIGIN", "Origin"),
        ("MSE_REFERER", "Referer"),
        ("MSE_USER_AGENT", "User-Agent"),
    ):
        value = os.environ.get(env_key)
        if value:
            headers[header_key] = value
    if "Origin" not in headers:
        headers["Origin"] = "https://mse.wemomo.com"
    if "Referer" not in headers:
        headers["Referer"] = "https://mse.wemomo.com/"
    return headers


def get_configs_by_namespace(
    *,
    base_url: str,
    cookie: str,
    region: str,
    app_key: str,
    name_space: str,
    cluster: str,
    env: str,
    config_key: str = "",
    order: bool = False,
    server: str = "config",
    timeout_s: float = 30.0,
) -> list[dict[str, Any]]:
    """调用 getConfigsByAppKeyAndNameSpace，返回 result 配置列表。"""
    root = base_url.rstrip("/")
    path = "/apirest/httpproxy/config/getConfigsByAppKeyAndNameSpace"
    url = f"{root}{path}"
    body = urllib.parse.urlencode(
        {
            "region": region,
            "appKey": app_key,
            "nameSpace": name_space,
            "cluster": cluster,
            "key": config_key or "",
            "order": "true" if order else "false",
            "env": env,
            "server": server,
        }
    ).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers=_headers(cookie))
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise RuntimeError(f"HTTP {exc.code}: {detail[:800]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"网络错误: {exc.reason}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"返回不是合法 JSON: {raw[:800]}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("返回 JSON 不是 object")

    ec = payload.get("ec")
    try:
        ec_int = int(ec)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"无法解析 ec: {ec}") from exc
    if ec_int not in (0, 200):
        em = payload.get("em")
        raise RuntimeError(f"配置接口失败: ec={ec_int}, em={em}")

    result = payload.get("result")
    if result is None:
        return []
    if not isinstance(result, list):
        raise RuntimeError("result 不是 array")
    return [item for item in result if isinstance(item, dict)]
