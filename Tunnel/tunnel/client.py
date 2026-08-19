"""Tunnel 抓包平台 HTTP 客户端。"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def build_auth_headers() -> dict[str, str]:
    cookie = _current_tunnel_cookie()
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


def _is_online_env() -> bool:
    return os.environ.get("ONLINE_ENV", "").strip().lower() in ("1", "true", "yes")


def _current_tunnel_cookie() -> str:
    if _is_online_env():
        cookie = os.environ.get("TUNNEL_ONLINE_COOKIE", "").strip()
        if cookie:
            return cookie
    cookie = os.environ.get("TUNNEL_COOKIE", "").strip()
    if cookie:
        return cookie
    if _is_online_env():
        return os.environ.get("MOA_ONLINE_COOKIE", "").strip()
    return os.environ.get("MOA_COOKIE", "").strip()


def _sync_tunnel_cookie_from_moa() -> str:
    moa_cookie = os.environ.get("MOA_COOKIE", "").strip()
    if moa_cookie:
        os.environ["TUNNEL_COOKIE"] = moa_cookie
    return _current_tunnel_cookie()


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
    """判断是否为认证/授权失败（需要刷新 Tunnel Cookie）。"""
    if code in (401, 403):
        return True
    if code == 302 and "aegis" in (body or "").lower():
        return True
    return _is_auth_body(body)


def _is_tunnel_business_auth_error(obj: dict[str, Any]) -> bool:
    ec = obj.get("ec")
    if ec in (401, "401", 403, "403"):
        return True
    em = str(obj.get("em", ""))
    return "登录" in em or "login" in em.lower()


def _try_auto_refresh_tunnel() -> bool:
    """通过 Aegis SSO 刷新 MOA/Tunnel Cookie，成功返回 True。"""
    repo_root = Path(__file__).resolve().parents[2]
    admin_dir = repo_root / "Admin"
    if str(admin_dir) not in sys.path:
        sys.path.insert(0, str(admin_dir))
    try:
        from admin.aegis_sso import auto_refresh_moa, update_env_local
        from admin.env import load_local_env, load_online_env

        load_local_env(str(admin_dir))
        online = _is_online_env()
        if online:
            load_online_env(str(admin_dir))
        sys.stderr.write("[Auto-Refresh] Tunnel Cookie 过期，正在通过 Aegis SSO 重新登录...\n")
        result = auto_refresh_moa(online=online)
        if not result.success:
            sys.stderr.write(f"[Auto-Refresh] 刷新失败: {result.error}\n")
            return False

        if not online:
            _sync_tunnel_cookie_from_moa()
            tunnel_env = repo_root / "Tunnel" / ".env.local"
            refreshed_cookie = os.environ.get("TUNNEL_COOKIE", "").strip()
            if refreshed_cookie and tunnel_env.exists():
                update_env_local(tunnel_env, {"TUNNEL_COOKIE": refreshed_cookie})

        user = result.username or result.momo_id or "unknown"
        sys.stderr.write(f"[Auto-Refresh] 刷新成功: user={user}\n")
        return True
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[Auto-Refresh] 异常: {exc}\n")
        return False


def _rebuild_request_with_cookie(req: urllib.request.Request, cookie: str) -> urllib.request.Request:
    headers = dict(req.headers)
    headers["Cookie"] = cookie
    return urllib.request.Request(
        url=req.full_url,
        data=req.data,
        method=req.get_method(),
        headers=headers,
    )


def http_get_json(url: str, *, timeout_s: float = 15.0, auto_refresh: bool = True) -> dict[str, Any]:
    req = urllib.request.Request(
        url=url,
        method="GET",
        headers=build_auth_headers(),
    )
    return _read_json_response(req, timeout_s=timeout_s, auto_refresh=auto_refresh)


def _read_json_response(
    req: urllib.request.Request,
    *,
    timeout_s: float,
    auto_refresh: bool = True,
    _retried: bool = False,
) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
        if not _retried and auto_refresh and _is_auth_error(e.code, raw):
            if _try_auto_refresh_tunnel():
                new_cookie = _sync_tunnel_cookie_from_moa()
                new_req = _rebuild_request_with_cookie(req, new_cookie)
                return _read_json_response(
                    new_req,
                    timeout_s=timeout_s,
                    auto_refresh=auto_refresh,
                    _retried=True,
                )
        raise RuntimeError(f"HTTP {e.code}: {raw}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误: {e}") from e

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        if not _retried and auto_refresh and _is_auth_body(raw):
            if _try_auto_refresh_tunnel():
                new_cookie = _sync_tunnel_cookie_from_moa()
                new_req = _rebuild_request_with_cookie(req, new_cookie)
                return _read_json_response(
                    new_req,
                    timeout_s=timeout_s,
                    auto_refresh=auto_refresh,
                    _retried=True,
                )
        raise RuntimeError(f"返回不是合法 JSON: {raw[:1000]}") from e
    if not isinstance(obj, dict):
        raise RuntimeError("返回 JSON 不是 object")

    if not _retried and auto_refresh and _is_tunnel_business_auth_error(obj):
        if _try_auto_refresh_tunnel():
            new_cookie = _sync_tunnel_cookie_from_moa()
            new_req = _rebuild_request_with_cookie(req, new_cookie)
            return _read_json_response(
                new_req,
                timeout_s=timeout_s,
                auto_refresh=auto_refresh,
                _retried=True,
            )

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
    auto_refresh: bool = True,
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
    return http_get_json(url, timeout_s=timeout_s, auto_refresh=auto_refresh)


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
