"""Web Agent 鉴权：钉钉验证码 Cookie 登录 + 可选 HTTP Basic Auth。"""

from __future__ import annotations

import base64
import ipaddress
import os
import sys
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler

_gateway = Path(__file__).resolve().parents[1] / "dingtalk_gateway"
if str(_gateway) not in sys.path:
    sys.path.insert(0, str(_gateway))

from env_loader import load_env_local
from web_otp_auth import (
    clear_session_cookie,
    current_web_user,
    is_public_auth_path,
    otp_auth_enabled,
    read_session_cookie,
    send_auth_required,
    send_login_redirect,
    set_session_cookie,
    get_web_otp_store,
)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _is_private_or_local(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return bool(addr.is_loopback or addr.is_private or addr.is_link_local)


def _effective_client_ip(handler: BaseHTTPRequestHandler) -> str:
    cf_ip = (handler.headers.get("CF-Connecting-IP") or "").strip()
    if cf_ip:
        return cf_ip
    forwarded = (handler.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    real_ip = (handler.headers.get("X-Real-IP") or "").strip()
    if real_ip:
        return real_ip
    return handler.client_address[0]


def _is_external_proxy_request(handler: BaseHTTPRequestHandler) -> bool:
    headers = handler.headers
    if headers.get("CF-Connecting-IP") or headers.get("CF-Ray") or headers.get("CF-Visitor"):
        return True
    host = (headers.get("Host") or "").lower()
    if any(token in host for token in ("trycloudflare.com", "ngrok", "ngrok-free.app", "ngrok.io")):
        return True
    forwarded = (headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    if forwarded and not _is_private_or_local(forwarded):
        return True
    return False


def auth_enabled() -> bool:
    """是否启用任意鉴权（OTP 或 Basic）。"""
    load_env_local()
    if otp_auth_enabled():
        return True
    user = os.environ.get("WEB_AGENT_AUTH_USER", "").strip()
    password = os.environ.get("WEB_AGENT_AUTH_PASSWORD", "").strip()
    return bool(user and password)


def auth_credentials() -> tuple[str, str] | None:
    load_env_local()
    user = os.environ.get("WEB_AGENT_AUTH_USER", "").strip()
    password = os.environ.get("WEB_AGENT_AUTH_PASSWORD", "").strip()
    if not user or not password:
        return None
    return user, password


def public_mode_required() -> bool:
    load_env_local()
    return _env_bool("WEB_AGENT_PUBLIC", False)


def auth_required_for_request(handler: BaseHTTPRequestHandler) -> bool:
    load_env_local()
    if otp_auth_enabled():
        return True
    if not auth_enabled():
        return False
    if not _env_bool("WEB_AGENT_AUTH_PUBLIC_ONLY", True):
        return True
    if _is_external_proxy_request(handler):
        return True
    return not _is_private_or_local(_effective_client_ip(handler))


def _client_ip(handler: BaseHTTPRequestHandler) -> str:
    return _effective_client_ip(handler)


def _ip_allowed(client_ip: str) -> bool:
    load_env_local()
    raw = os.environ.get("WEB_AGENT_ALLOW_IPS", "").strip()
    if not raw:
        return True
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        try:
            if "/" in item:
                if addr in ipaddress.ip_network(item, strict=False):
                    return True
            elif addr == ipaddress.ip_address(item):
                return True
        except ValueError:
            continue
    return False


def _send_unauthorized(handler: BaseHTTPRequestHandler, *, realm: str = "Web Agent") -> None:
    handler.send_response(HTTPStatus.UNAUTHORIZED)
    handler.send_header("WWW-Authenticate", f'Basic realm="{realm}", charset="UTF-8"')
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    body = "需要登录鉴权\n".encode("utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _send_forbidden(handler: BaseHTTPRequestHandler) -> None:
    handler.send_response(HTTPStatus.FORBIDDEN)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    body = "IP 不在白名单\n".encode("utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _basic_auth_valid(handler: BaseHTTPRequestHandler) -> bool:
    creds = auth_credentials()
    if creds is None:
        return False
    auth_header = handler.headers.get("Authorization") or ""
    if not auth_header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth_header[6:].strip(), validate=True).decode("utf-8")
        user, sep, password = decoded.partition(":")
        if not sep:
            return False
    except (ValueError, UnicodeDecodeError):
        return False
    expected_user, expected_password = creds
    return user == expected_user and password == expected_password


def authorize_request(handler: BaseHTTPRequestHandler) -> bool:
    """返回 True 表示可继续处理请求。"""
    load_env_local()
    path = (getattr(handler, "path", "") or "").split("?", 1)[0].rstrip("/") or "/"

    if public_mode_required() and not auth_enabled():
        handler.send_response(HTTPStatus.SERVICE_UNAVAILABLE)
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        body = "外网模式未配置鉴权\n".encode("utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
        return False

    client_ip = _client_ip(handler)
    if not _ip_allowed(client_ip):
        _send_forbidden(handler)
        return False

    if is_public_auth_path(path):
        return True

    if otp_auth_enabled():
        if current_web_user(handler) is not None:
            return True
        if _basic_auth_valid(handler):
            return True
        json_api = path.startswith("/api/")
        send_auth_required(handler, json_api=json_api)
        return False

    if not auth_required_for_request(handler):
        return True

    if _basic_auth_valid(handler):
        return True

    _send_unauthorized(handler)
    return False


def logout_current_session(handler: BaseHTTPRequestHandler) -> None:
    token = read_session_cookie(handler)
    if token:
        get_web_otp_store().revoke_session_token(token)
    clear_session_cookie(handler)
