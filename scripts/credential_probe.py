#!/usr/bin/env python3
"""各模块 Cookie / Token 在线探活（doctor / 钉钉网关 health 共用）。"""

from __future__ import annotations

import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from mcp_paths import load_mcp_env, resolve_dingtalk_cookie  # noqa: E402

_DEFAULT_PROBE_NODE = "jb9Y4gmKWr7wodldCZEEZ3n1VGXn6lpz"
_ALIDOCS_BASE = "https://alidocs.dingtalk.com"
_BOX_LIST_API = f"{_ALIDOCS_BASE}/box/api/v2/dentry/list"
_EXCEL_TOKEN_API = "http://gaia-hg.momo.com/ding/excel/token"
_DINGTALK_OAUTH_URL = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
_PROBE_USER_ID = "100000001"


@dataclass(frozen=True)
class ProbeResult:
    name: str
    status: str  # ok | fail | skip
    detail: str
    required: bool = False


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def validate_dingtalk_doc_cookie_format(cookie: str) -> list[str]:
    text = " ".join((cookie or "").split())
    issues: list[str] = []
    if not text:
        issues.append("Cookie 为空")
        return issues
    if "doc_atoken=" not in text:
        issues.append("缺少 doc_atoken")
    if "XSRF-TOKEN=" not in text:
        issues.append("缺少 XSRF-TOKEN")
    if len(text) < 80:
        issues.append("Cookie 过短，可能复制不完整")
    return issues


def probe_dingtalk_doc_cookie(
    cookie: str | None = None,
    *,
    node_id: str = _DEFAULT_PROBE_NODE,
    timeout_s: float = 30.0,
) -> tuple[bool, str]:
    """钉钉文档 Cookie（alidocs Box API）。"""
    try:
        ck = (cookie or resolve_dingtalk_cookie()).strip()
    except RuntimeError as exc:
        return False, str(exc)

    issues = validate_dingtalk_doc_cookie_format(ck)
    if issues:
        return False, "；".join(issues)

    xsrf_m = re.search(r"XSRF-TOKEN=([^;]+)", ck)
    xsrf = xsrf_m.group(1) if xsrf_m else ""
    params = urllib.parse.urlencode(
        {
            "dentryUuid": node_id,
            "orderType": "SORT_KEY",
            "sortType": "desc",
            "listDentrySource": "2",
            "pageSize": 1,
        }
    )
    url = f"{_BOX_LIST_API}?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "cookie": ck,
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "accept": "application/json, text/plain, */*",
            "referer": f"{_ALIDOCS_BASE}/i/nodes/{node_id}",
            "x-xsrf-token": xsrf,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, context=_ssl_context(), timeout=timeout_s) as response:
            status = response.status
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, f"HTTP {exc.code}，Cookie 无效或已过期"
        return False, f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return False, f"网络错误: {exc.reason}"

    if status >= 400:
        return False, f"HTTP {status}"
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False, "响应非 JSON，可能已跳转登录页"
    if not payload.get("isSuccess", True) and payload.get("status") not in (200, None):
        return False, f"API 返回失败: {payload.get('status')}"
    return True, "钉钉文档 Cookie 有效"


def probe_dingtalk_excel_aegis(
  *,
  aegis_key: str | None = None,
  aegis_secret: str | None = None,
  workid: str | None = None,
  timeout_s: float = 20.0,
) -> tuple[bool, str]:
    """钉钉 Excel OpenAPI（Aegis Key/Secret + workid）。"""
    env: dict[str, str] = {}
    for server_key in ("dingtalk-excel-read", "dingtalk-excel-write", "user-dingtalk-excel-read"):
        env = load_mcp_env(server_key)
        if env:
            break

    key = (aegis_key or env.get("DINGTALK_AEGIS_KEY") or "").strip()
    secret = (aegis_secret or env.get("DINGTALK_AEGIS_SECRET") or "").strip()
    wid = (workid or env.get("DINGTALK_WORKID") or "").strip()
    if not key or not secret or not wid:
        return False, "未配置 DINGTALK_AEGIS_KEY / DINGTALK_AEGIS_SECRET / DINGTALK_WORKID"

    params = urllib.parse.urlencode({"aegisKey": key, "aegisSecret": secret, "workid": wid})
    url = f"{_EXCEL_TOKEN_API}?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.84 Safari/537.36"
            ),
            "content-type": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return False, f"HTTP {exc.code}: {raw[:200]}"
    except urllib.error.URLError as exc:
        return False, f"网络错误: {exc.reason}"

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False, "响应非 JSON"
    if payload.get("ec") == 200 and payload.get("data", {}).get("token"):
        return True, "钉钉 Excel Aegis 凭证有效"
    em = payload.get("em") or payload.get("message") or "未知错误"
    return False, f"Aegis 凭证无效: ec={payload.get('ec')} {em}"


def probe_moa_cookie(*, timeout_s: int = 30) -> tuple[bool, str]:
    """MOA 测试环境 Cookie。"""
    cmd = [
        sys.executable,
        str(ROOT / "MOA" / "moa_execute.py"),
        "--payload-file",
        str(ROOT / "MOA" / "templates" / "VIP-增加经验值.json"),
        "--vip-user-id",
        _PROBE_USER_ID,
        "--vip-query-current",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return False, "MOA 探活超时"

    output = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    if "Aegis SSO" in output or "<!doctype html>" in output.lower():
        return False, "MOA Cookie 已过期，请登录 https://mse.wemomo.com 后更新 MOA/.env.local"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:300]
        return False, detail or f"MOA 探活失败 exit={proc.returncode}"
    return True, "MOA 测试环境可用"


def _ensure_admin_path() -> None:
    admin_dir = str(ROOT / "Admin")
    if admin_dir not in sys.path:
        sys.path.insert(0, admin_dir)


def probe_admin_token(*, timeout_s: float = 15.0) -> tuple[bool, str]:
    """Admin 测试环境 sso-token + yaahlan-jwt。"""
    _ensure_admin_path()
    from admin.client import admin_success, http_post_json
    from admin.config import defaults as admin_defaults
    from admin.env import load_local_env

    load_local_env(str(ROOT / "Admin"))
    sso = os.environ.get("ADMIN_SSO_TOKEN", "").strip()
    jwt = os.environ.get("ADMIN_YAAHLAN_JWT", "").strip()
    if not sso or not jwt:
        return False, "未配置 ADMIN_SSO_TOKEN / ADMIN_YAAHLAN_JWT（Admin/.env.local）"

    api = admin_defaults("api")
    path = admin_defaults("query_user_detail").get("path", "/admin/user/queryUserDetail")
    base_url = os.environ.get("ADMIN_BASE_URL", "").strip() or str(api.get("baseUrl") or "")
    if not base_url:
        return False, "缺少 ADMIN_BASE_URL"
    url = f"{base_url.rstrip('/')}{path}"

    try:
        resp = http_post_json(url, {"userId": _PROBE_USER_ID}, timeout_s=timeout_s)
    except (RuntimeError, ValueError) as exc:
        msg = str(exc)
        if "401" in msg or "403" in msg or "sso" in msg.lower():
            return False, "Admin Token 已过期，请重新抓包更新 Admin/.env.local"
        return False, msg[:300]

    if admin_success(resp.get("ec")):
        return True, "Admin 测试环境 Token 有效"
    em = resp.get("em") or resp.get("message") or ""
    if str(resp.get("ec")) in ("401", "403"):
        return False, "Admin Token 已过期，请重新抓包更新 Admin/.env.local"
    return False, f"Admin 探活失败: ec={resp.get('ec')} {em}"[:200]


def _ensure_tunnel_path() -> None:
    tunnel_dir = str(ROOT / "Tunnel")
    if tunnel_dir not in sys.path:
        sys.path.insert(0, tunnel_dir)


def probe_tunnel_cookie(*, timeout_s: float = 15.0) -> tuple[bool, str]:
    """Tunnel 测试环境 Cookie（可复用 MOA_COOKIE）。"""
    _ensure_tunnel_path()
    from tunnel.client import list_requests, tunnel_success
    from tunnel.env import load_local_env

    load_local_env(str(ROOT / "Tunnel"))
    cookie = os.environ.get("TUNNEL_COOKIE", "").strip()
    if not cookie:
        return False, "未配置 TUNNEL_COOKIE（可写入 Tunnel/.env.local 或复用 MOA_COOKIE）"

    base_url = os.environ.get("TUNNEL_BASE_URL", "https://tunnel.wemomo.com").strip()
    g_env = os.environ.get("TUNNEL_G_ENV", "alpha").strip() or "alpha"
    g_appid = os.environ.get("TUNNEL_G_APPID", "All").strip() or "All"
    start_time = int(time.time()) - 3600

    try:
        resp = list_requests(
            base_url=base_url,
            momoid=_PROBE_USER_ID,
            start_time=start_time,
            g_env=g_env,
            g_appid=g_appid,
            timeout_s=timeout_s,
        )
    except (RuntimeError, ValueError) as exc:
        msg = str(exc)
        if "401" in msg or "403" in msg or "<!doctype" in msg.lower():
            return False, "Tunnel Cookie 已过期，请登录 tunnel.wemomo.com 或更新 MOA_COOKIE"
        return False, msg[:300]

    if tunnel_success(resp.get("ec")):
        return True, "Tunnel 测试环境 Cookie 有效"
    if "<!doctype" in json.dumps(resp, ensure_ascii=False).lower():
        return False, "Tunnel Cookie 已过期，返回登录页"
    return False, f"Tunnel 探活失败: ec={resp.get('ec')}"


def probe_dingtalk_open_platform(
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    timeout_s: float = 20.0,
) -> tuple[bool, str]:
    """钉钉开放平台 appKey/appSecret（网关 Stream + 文件上传）。"""
    cid = (client_id or os.environ.get("DINGTALK_CLIENT_ID") or "").strip()
    secret = (client_secret or os.environ.get("DINGTALK_CLIENT_SECRET") or "").strip()
    if not cid or not secret:
        return False, "未配置 DINGTALK_CLIENT_ID / DINGTALK_CLIENT_SECRET"

    data = json.dumps({"appKey": cid, "appSecret": secret}).encode("utf-8")
    req = urllib.request.Request(
        _DINGTALK_OAUTH_URL,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return False, f"HTTP {exc.code}: {raw[:200]}"
    except urllib.error.URLError as exc:
        return False, f"网络错误: {exc.reason}"

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False, "响应非 JSON"
    token = payload.get("accessToken")
    if token:
        return True, "钉钉开放平台凭证有效"
    code = payload.get("code") or payload.get("errcode")
    msg = payload.get("message") or payload.get("errmsg") or "未知错误"
    return False, f"开放平台凭证无效: {code} {msg}"


def _mcp_env_configured(server_key: str, keys: tuple[str, ...]) -> bool:
    env = load_mcp_env(server_key)
    return bool(env) and all(env.get(k, "").strip() for k in keys)


def _env_file_has(path: Path, key: str) -> bool:
    if not path.is_file():
        return False
    prefix = f"{key}="
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(prefix) and line[len(prefix) :].strip():
            return True
    return False


def _run_named_probe(
    name: str,
    probe_fn: Callable[[], tuple[bool, str]],
    *,
    configured: bool,
    required: bool,
) -> ProbeResult:
    if not configured:
        return ProbeResult(name, "skip", "未配置", required=required)
    ok, detail = probe_fn()
    return ProbeResult(name, "ok" if ok else "fail", detail, required=required)


def run_all_credential_probes() -> list[ProbeResult]:
    """按网关依赖顺序探活全部凭证。"""
    gateway_env = ROOT / "platform" / "dingtalk_gateway" / ".env.local"
    moa_env = ROOT / "MOA" / ".env.local"
    admin_env = ROOT / "Admin" / ".env.local"
    tunnel_env = ROOT / "Tunnel" / ".env.local"

    # 预加载网关 .env.local（不覆盖已有环境变量）
    if gateway_env.is_file():
        for raw in gateway_env.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value

    doc_configured = False
    try:
        resolve_dingtalk_cookie()
        doc_configured = True
    except RuntimeError:
        doc_configured = False

    excel_configured = any(
        _mcp_env_configured(
            key,
            ("DINGTALK_AEGIS_KEY", "DINGTALK_AEGIS_SECRET", "DINGTALK_WORKID"),
        )
        for key in ("dingtalk-excel-read", "dingtalk-excel-write", "user-dingtalk-excel-read")
    )

    probes: list[ProbeResult] = [
        _run_named_probe(
            "钉钉文档 Cookie",
            lambda: probe_dingtalk_doc_cookie(),
            configured=doc_configured,
            required=True,
        ),
        _run_named_probe(
            "钉钉 Excel Aegis",
            lambda: probe_dingtalk_excel_aegis(),
            configured=excel_configured,
            required=True,
        ),
        _run_named_probe(
            "MOA Cookie",
            probe_moa_cookie,
            configured=_env_file_has(moa_env, "MOA_COOKIE"),
            required=True,
        ),
        _run_named_probe(
            "Admin Token",
            probe_admin_token,
            configured=_env_file_has(admin_env, "ADMIN_SSO_TOKEN")
            and _env_file_has(admin_env, "ADMIN_YAAHLAN_JWT"),
            required=False,
        ),
        _run_named_probe(
            "Tunnel Cookie",
            probe_tunnel_cookie,
            configured=_env_file_has(tunnel_env, "TUNNEL_COOKIE") or _env_file_has(moa_env, "MOA_COOKIE"),
            required=False,
        ),
        _run_named_probe(
            "钉钉开放平台",
            lambda: probe_dingtalk_open_platform(),
            configured=_env_file_has(gateway_env, "DINGTALK_CLIENT_ID")
            and _env_file_has(gateway_env, "DINGTALK_CLIENT_SECRET"),
            required=True,
        ),
    ]
    return probes


def format_probe_line(result: ProbeResult) -> str:
    if result.status == "skip":
        mark = "SKIP"
    elif result.status == "ok":
        mark = "OK"
    elif result.required:
        mark = "FAIL"
    else:
        mark = "WARN"
    return f"  [{mark}] {result.name}: {result.detail}"


def print_credential_probes() -> bool:
    """打印探活结果；返回是否全部必检项通过。"""
    print("=== 凭证有效性 ===")
    ok_all = True
    for result in run_all_credential_probes():
        print(format_probe_line(result))
        if result.status == "fail" and result.required:
            ok_all = False
    return ok_all
