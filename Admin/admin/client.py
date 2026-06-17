"""Yaahlan Admin HTTP 客户端。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def build_mdp_nova_headers() -> dict[str, str]:
    """MDP Nova 礼物后台（Cookie 鉴权）。"""
    aegis_token = os.environ.get("MDP_AEGIS_TOKEN", "").strip()
    cloud_token = os.environ.get("MDP_CLOUD_AEGIS_TOKEN", "").strip()
    if not aegis_token:
        raise ValueError("缺少 MDP_AEGIS_TOKEN（请写入 Admin/.env.local，抓包 alpha_mdp_aegis_token）")
    if not cloud_token:
        raise ValueError("缺少 MDP_CLOUD_AEGIS_TOKEN（请写入 Admin/.env.local，抓包 CLOUD-AEGIS-TOKEN）")

    cookie_parts = [
        f"alpha_mdp_aegis_token={aegis_token}",
        f"CLOUD-AEGIS-TOKEN={cloud_token}",
    ]
    extra_cookie = os.environ.get("MDP_ADMIN_COOKIE_EXTRA", "").strip()
    if extra_cookie:
        cookie_parts.append(extra_cookie)

    headers: dict[str, str] = {
        "Cookie": "; ".join(cookie_parts),
        "Origin": os.environ.get("MDP_ADMIN_ORIGIN", "https://mdp-nova-alpha.wemomo.com").strip()
        or "https://mdp-nova-alpha.wemomo.com",
        "Referer": os.environ.get("MDP_ADMIN_REFERER", "https://mdp-nova-alpha.wemomo.com/").strip()
        or "https://mdp-nova-alpha.wemomo.com/",
    }
    user_agent = os.environ.get("MDP_ADMIN_USER_AGENT", "").strip()
    if user_agent:
        headers["User-Agent"] = user_agent
    return headers


def _build_yaahlan_auth_headers(
    *,
    sso_env: str,
    jwt_env: str,
    lang_env: str,
    origin_env: str,
    referer_env: str,
    user_agent_env: str,
    env_file_hint: str,
    default_origin: str = "",
    default_referer: str = "",
) -> dict[str, str]:
    headers: dict[str, str] = {}
    sso_token = os.environ.get(sso_env, "").strip()
    yaahlan_jwt = os.environ.get(jwt_env, "").strip()
    if not sso_token:
        raise ValueError(f"缺少 {sso_env}（请写入 {env_file_hint}）")
    if not yaahlan_jwt:
        raise ValueError(f"缺少 {jwt_env}（请写入 {env_file_hint}）")

    headers["sso-token"] = sso_token
    headers["yaahlan-jwt"] = yaahlan_jwt
    headers["yaahlan-lang"] = os.environ.get(lang_env, "zh").strip() or "zh"

    origin = os.environ.get(origin_env, default_origin).strip() or default_origin
    referer = os.environ.get(referer_env, default_referer).strip() or default_referer
    if origin:
        headers["Origin"] = origin
    if referer:
        headers["Referer"] = referer

    user_agent = os.environ.get(user_agent_env, "").strip()
    if user_agent:
        headers["User-Agent"] = user_agent
    return headers


def build_auth_headers() -> dict[str, str]:
    return _build_yaahlan_auth_headers(
        sso_env="ADMIN_SSO_TOKEN",
        jwt_env="ADMIN_YAAHLAN_JWT",
        lang_env="ADMIN_LANG",
        origin_env="ADMIN_ORIGIN",
        referer_env="ADMIN_REFERER",
        user_agent_env="ADMIN_USER_AGENT",
        env_file_hint="Admin/.env.local",
    )


def build_online_auth_headers() -> dict[str, str]:
    return _build_yaahlan_auth_headers(
        sso_env="ADMIN_ONLINE_SSO_TOKEN",
        jwt_env="ADMIN_ONLINE_YAAHLAN_JWT",
        lang_env="ADMIN_ONLINE_LANG",
        origin_env="ADMIN_ONLINE_ORIGIN",
        referer_env="ADMIN_ONLINE_REFERER",
        user_agent_env="ADMIN_ONLINE_USER_AGENT",
        env_file_hint="online/.env.local",
        default_origin="https://www.yaahlan.fun",
        default_referer="https://www.yaahlan.fun/",
    )


def http_post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout_s: float = 10.0,
    auth: str = "yaahlan",
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if auth == "mdp_nova":
        extra_headers = build_mdp_nova_headers()
    elif auth == "yaahlan":
        extra_headers = build_auth_headers()
    elif auth == "yaahlan_online":
        extra_headers = build_online_auth_headers()
    else:
        raise ValueError(f"未知 auth 模式: {auth}")

    req_headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        **extra_headers,
    }

    req = urllib.request.Request(url=url, data=body, method="POST", headers=req_headers)
    return _read_json_response(req, timeout_s=timeout_s)


def http_get_json(
    url: str,
    *,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    req_headers: dict[str, str] = {
        "Accept": "application/json, text/plain, */*",
        **build_auth_headers(),
    }
    req = urllib.request.Request(url=url, method="GET", headers=req_headers)
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


def admin_success(ec: Any) -> bool:
    try:
        return int(ec) == 200
    except (TypeError, ValueError):
        return False
