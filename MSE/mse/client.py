"""MSE 配置中心 HTTP 客户端。"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _is_auth_body(body: str) -> bool:
    lower = (body or "").lower()
    if "aegis sso" in lower:
        return True
    if "login" in lower and "sso" in lower:
        return True
    if "<!doctype html>" in lower and ("aegis" in lower or "login" in lower):
        return True
    return False


def _is_auth_error(code: int, body: str) -> bool:
    if code in (401, 403):
        return True
    if code == 302 and "aegis" in (body or "").lower():
        return True
    return _is_auth_body(body)


def _current_mse_cookie(fallback: str) -> str:
    for key in ("MSE_COOKIE", "MOA_COOKIE", "MOA_ONLINE_COOKIE"):
        refreshed = os.environ.get(key, "").strip()
        if refreshed:
            return refreshed
    return fallback


def _try_auto_refresh_mse() -> bool:
    """通过 Aegis SSO 刷新 MOA/MSE Cookie，成功返回 True。"""
    repo_root = Path(__file__).resolve().parents[2]
    admin_dir = repo_root / "Admin"
    if str(admin_dir) not in sys.path:
        sys.path.insert(0, str(admin_dir))
    try:
        from admin.aegis_sso import auto_refresh_moa
        from admin.env import load_local_env

        load_local_env(str(admin_dir))
        sys.stderr.write("[Auto-Refresh] MSE Cookie 过期，正在通过 Aegis SSO 重新登录...\n")
        result = auto_refresh_moa()
        if result.success:
            user = result.username or result.momo_id or "unknown"
            sys.stderr.write(f"[Auto-Refresh] 刷新成功: user={user}\n")
            return True
        sys.stderr.write(f"[Auto-Refresh] 刷新失败: {result.error}\n")
        return False
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[Auto-Refresh] 异常: {exc}\n")
        return False


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


def _rebuild_request_with_cookie(req: urllib.request.Request, cookie: str) -> urllib.request.Request:
    headers = dict(req.headers)
    headers["Cookie"] = cookie
    return urllib.request.Request(
        url=req.full_url,
        data=req.data,
        method=req.get_method(),
        headers=headers,
    )


def _post_configs_request(
    req: urllib.request.Request,
    *,
    timeout_s: float,
    auto_refresh: bool = True,
    _retried: bool = False,
) -> list[dict[str, Any]]:
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        if not _retried and auto_refresh and _is_auth_error(exc.code, detail):
            if _try_auto_refresh_mse():
                new_cookie = _current_mse_cookie("")
                new_req = _rebuild_request_with_cookie(req, new_cookie)
                return _post_configs_request(
                    new_req,
                    timeout_s=timeout_s,
                    auto_refresh=auto_refresh,
                    _retried=True,
                )
        raise RuntimeError(f"HTTP {exc.code}: {detail[:800]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"网络错误: {exc.reason}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        if not _retried and auto_refresh and _is_auth_body(raw):
            if _try_auto_refresh_mse():
                new_cookie = _current_mse_cookie("")
                new_req = _rebuild_request_with_cookie(req, new_cookie)
                return _post_configs_request(
                    new_req,
                    timeout_s=timeout_s,
                    auto_refresh=auto_refresh,
                    _retried=True,
                )
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
    auto_refresh: bool = True,
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
    cookie = _current_mse_cookie(cookie)
    req = urllib.request.Request(url, data=body, method="POST", headers=_headers(cookie))
    return _post_configs_request(req, timeout_s=timeout_s, auto_refresh=auto_refresh)
