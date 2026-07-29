"""Tunnel 抓包平台 Mock API（/api/mock_cases、/api/param_mock）。"""

from __future__ import annotations

import json
from typing import Any

from .client import build_auth_headers, http_get_json, tunnel_success


def _api_json(
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    base_url: str = "https://tunnel.wemomo.com",
    timeout_s: float = 15.0,
) -> dict[str, Any]:
    import urllib.error
    import urllib.parse
    import urllib.request

    url = f"{base_url.rstrip('/')}/api{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    data = None
    headers = build_auth_headers()
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {**headers, "Content-Type": "application/json"}

    req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
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


def require_tunnel_ok(payload: dict[str, Any], *, action: str) -> dict[str, Any]:
    if not tunnel_success(payload.get("ec")):
        raise RuntimeError(f"{action} 失败: ec={payload.get('ec')} em={payload.get('em')}")
    return payload


def normalize_uri(uri: str) -> str:
    value = uri.strip()
    if not value:
        raise ValueError("uri 不能为空")
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("/"):
        return f"http://gw-api-alpha.yaahlan.fun{value}"
    return f"http://gw-api-alpha.yaahlan.fun/{value.lstrip('/')}"


def _env_params(*, g_appid: str = "All", g_env: str = "alpha") -> dict[str, str]:
    return {"g_appid": g_appid, "g_env": g_env}


def list_mock_cases(
    *,
    uri: str,
    momoid: str,
    app_id: str = "All",
    g_appid: str = "All",
    g_env: str = "alpha",
    base_url: str = "https://tunnel.wemomo.com",
) -> list[dict[str, Any]]:
    payload = require_tunnel_ok(
        _api_json(
            "GET",
            "/mock_cases",
            params={
                "uri": normalize_uri(uri),
                "momoid": momoid,
                "appId": app_id,
                **_env_params(g_appid=g_appid, g_env=g_env),
            },
            base_url=base_url,
        ),
        action="查询 mock_cases",
    )
    data = payload.get("data")
    return data if isinstance(data, list) else []


def create_mock_case(
    *,
    uri: str,
    momoid: str,
    response_json: str | dict[str, Any],
    app_id: str = "All",
    g_appid: str = "All",
    g_env: str = "alpha",
    index: int = 0,
    name: str = "",
    enable: bool = True,
    base_url: str = "https://tunnel.wemomo.com",
) -> dict[str, Any]:
    if isinstance(response_json, dict):
        json_text = json.dumps(response_json, ensure_ascii=False)
    else:
        json_text = response_json.strip()
        json.loads(json_text)

    body = {
        "uri": normalize_uri(uri),
        "json": json_text,
        "index": index,
        "name": name,
        "momoid": momoid,
        "appId": app_id,
        "enable": 1 if enable else 0,
    }
    return require_tunnel_ok(
        _api_json(
            "POST",
            "/mock_cases",
            params=_env_params(g_appid=g_appid, g_env=g_env),
            body=body,
            base_url=base_url,
        ),
        action="创建 mock_case",
    )


def toggle_mock_case(
    *,
    uri: str,
    momoid: str,
    action: str,
    app_id: str = "All",
    g_appid: str = "All",
    g_env: str = "alpha",
    index: int | None = None,
    base_url: str = "https://tunnel.wemomo.com",
) -> dict[str, Any]:
    if action not in {"start", "stop"}:
        raise ValueError("action 必须是 start 或 stop")
    body: dict[str, Any] = {
        "uri": normalize_uri(uri),
        "momoid": momoid,
        "appId": app_id,
        "action": action,
    }
    if index is not None:
        body["index"] = index
    return require_tunnel_ok(
        _api_json(
            "PATCH",
            "/mock_cases",
            params=_env_params(g_appid=g_appid, g_env=g_env),
            body=body,
            base_url=base_url,
        ),
        action=f"{'启用' if action == 'start' else '停用'} mock_case",
    )


def delete_mock_case(
    *,
    uri: str,
    momoid: str,
    index: int,
    app_id: str = "All",
    g_appid: str = "All",
    g_env: str = "alpha",
    base_url: str = "https://tunnel.wemomo.com",
) -> dict[str, Any]:
    body = {
        "uri": normalize_uri(uri),
        "momoid": momoid,
        "appId": app_id,
        "index": index,
    }
    return require_tunnel_ok(
        _api_json(
            "DELETE",
            "/mock_cases",
            params=_env_params(g_appid=g_appid, g_env=g_env),
            body=body,
            base_url=base_url,
        ),
        action="删除 mock_case",
    )


def list_param_mocks(
    *,
    uri: str,
    momoid: str,
    base_url: str = "https://tunnel.wemomo.com",
) -> list[dict[str, Any]]:
    payload = require_tunnel_ok(
        _api_json(
            "GET",
            "/param_mock",
            params={"uri": normalize_uri(uri), "momoid": momoid},
            base_url=base_url,
        ),
        action="查询 param_mock",
    )
    data = payload.get("data")
    return data if isinstance(data, list) else []


def set_param_mock(
    *,
    uri: str,
    momoid: str,
    param_key: str,
    param_value: str,
    base_url: str = "https://tunnel.wemomo.com",
) -> dict[str, Any]:
    body = {
        "uri": normalize_uri(uri),
        "momoid": momoid,
        "param_key": param_key.strip(),
        "param_value": str(param_value),
    }
    payload = _api_json("POST", "/param_mock", body=body, base_url=base_url)
    ec = payload.get("ec")
    if ec not in (200, 201):
        raise RuntimeError(f"设置 param_mock 失败: ec={ec} em={payload.get('em')}")
    return payload


def delete_param_mock(
    *,
    uri: str,
    momoid: str,
    param_key: str,
    base_url: str = "https://tunnel.wemomo.com",
) -> dict[str, Any]:
    body = {
        "uri": normalize_uri(uri),
        "momoid": momoid,
        "param_key": param_key.strip(),
    }
    return require_tunnel_ok(
        _api_json("DELETE", "/param_mock", body=body, base_url=base_url),
        action="删除 param_mock",
    )


def find_latest_capture(
    *,
    base_url: str,
    momoid: str,
    keyword: str,
    since_s: int = 3600,
    url_contains: str = "",
) -> dict[str, Any]:
    import time

    from .client import list_requests, normalize_request_list

    payload = list_requests(
        base_url=base_url,
        momoid=momoid,
        start_time=int(time.time()) - since_s,
        keyword=keyword,
    )
    if not tunnel_success(payload.get("ec")):
        raise RuntimeError(f"抓包查询失败: ec={payload.get('ec')} em={payload.get('em')}")

    items = normalize_request_list(payload)
    needle = url_contains or keyword
    if needle:
        items = [x for x in items if needle in str(x.get("url", ""))]
    if not items:
        raise RuntimeError(
            f"未找到 momoid={momoid} keyword={keyword!r} url_contains={url_contains!r} 的抓包（since={since_s}s）"
        )

    return sorted(items, key=lambda x: str(x.get("time", "")), reverse=True)[0]
