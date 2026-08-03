"""网页版钉钉验证码登录：OTP 签发、Cookie 会话、落盘共享（网关 + Web 服务）。"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler

WEB_AGENT_DIR = Path(__file__).resolve().parent
DATA_DIR = WEB_AGENT_DIR / "data"
OTP_STORE_PATH = DATA_DIR / "web_otp_store.json"
SESSION_STORE_PATH = DATA_DIR / "web_auth_sessions.json"

WEB_LOGIN_PHRASE = "请求访问Yaahlan 智能工具 Agent"
WEB_LOGIN_RE = re.compile(
    r"^请求访问\s*Yaahlan\s*智能工具\s*Agent\s*$",
    re.I,
)
COOKIE_NAME = "web_agent_session"
OTP_LENGTH = 8
OTP_TTL_S = 300
SESSION_TTL_S = 30 * 86400
OTP_RATE_LIMIT_S = 60
MAX_OTP_ATTEMPTS = 8
DEFAULT_MASTER_OTP = "19910907"

logger = logging.getLogger("web-agent")


@dataclass(frozen=True)
class WebAuthUser:
    staff_id: str
    display_name: str = ""
    auth_created_at: float = 0.0


def otp_auth_enabled() -> bool:
    raw = os.environ.get("WEB_AGENT_OTP_AUTH", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def master_otp_enabled() -> bool:
    raw = os.environ.get("WEB_AGENT_MASTER_OTP", DEFAULT_MASTER_OTP).strip()
    return bool(raw) and raw.lower() not in ("0", "false", "no", "off")


def master_otp_code() -> str:
    return os.environ.get("WEB_AGENT_MASTER_OTP", DEFAULT_MASTER_OTP).strip()


def is_web_login_request(text: str) -> bool:
    return bool(WEB_LOGIN_RE.match((text or "").strip()))


LOGIN_PUBLIC_STATIC_PATHS = frozenset(
    {
        "/theme.js",
        "/dingtalk_oauth.js",
    }
)


def is_public_auth_path(path: str) -> bool:
    p = (path or "").rstrip("/") or "/"
    if p in ("/login.html", "/login"):
        return True
    if p in ("/keynote", "/platform-guide"):
        return True
    if p.startswith("/keynote/") or p.startswith("/platform-guide/"):
        return True
    if p.startswith("/assets/fonts/"):
        return True
    if p in LOGIN_PUBLIC_STATIC_PATHS:
        return True
    if p.startswith("/api/auth/"):
        return True
    return False


class WebOtpAuthStore:
    def __init__(
        self,
        otp_path: Path = OTP_STORE_PATH,
        session_path: Path = SESSION_STORE_PATH,
    ) -> None:
        self._otp_path = otp_path
        self._session_path = session_path
        self._lock = threading.Lock()

    def _load_otps(self) -> dict[str, dict[str, object]]:
        if not self._otp_path.is_file():
            return {}
        try:
            raw = json.loads(self._otp_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取 web_otp_store.json 失败: %s", exc)
            return {}
        return raw if isinstance(raw, dict) else {}

    def _save_otps(self, data: dict[str, dict[str, object]]) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._otp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_sessions(self) -> dict[str, dict[str, object]]:
        if not self._session_path.is_file():
            return {}
        try:
            raw = json.loads(self._session_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取 web_auth_sessions.json 失败: %s", exc)
            return {}
        return raw if isinstance(raw, dict) else {}

    def _save_sessions(self, data: dict[str, dict[str, object]]) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._session_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _purge_expired_locked(
        self,
        otps: dict[str, dict[str, object]],
        sessions: dict[str, dict[str, object]],
    ) -> None:
        now = time.time()
        for code in list(otps.keys()):
            item = otps.get(code) or {}
            try:
                expires = float(item.get("expiresAt") or 0)
            except (TypeError, ValueError):
                expires = 0
            if expires <= now or item.get("used"):
                otps.pop(code, None)
        for token in list(sessions.keys()):
            item = sessions.get(token) or {}
            try:
                expires = float(item.get("expiresAt") or 0)
            except (TypeError, ValueError):
                expires = 0
            if expires <= now:
                sessions.pop(token, None)

    def issue_otp(self, staff_id: str, *, display_name: str = "") -> tuple[str | None, str | None]:
        """签发 8 位验证码；返回 (code, error_message)。"""
        uid = (staff_id or "").strip()
        if not uid:
            return None, "缺少钉钉用户标识，无法签发验证码"
        now = time.time()
        with self._lock:
            otps = self._load_otps()
            sessions = self._load_sessions()
            self._purge_expired_locked(otps, sessions)
            for item in otps.values():
                if str(item.get("staffId") or "") != uid:
                    continue
                try:
                    issued_at = float(item.get("issuedAt") or 0)
                except (TypeError, ValueError):
                    issued_at = 0
                if now - issued_at < OTP_RATE_LIMIT_S:
                    return None, f"请 {int(OTP_RATE_LIMIT_S - (now - issued_at))} 秒后再试"
            for code, item in list(otps.items()):
                if str(item.get("staffId") or "") == uid:
                    otps.pop(code, None)
            for token, item in list(sessions.items()):
                if str(item.get("staffId") or "") == uid:
                    sessions.pop(token, None)
            code = f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"
            otps[code] = {
                "staffId": uid,
                "displayName": (display_name or "").strip(),
                "issuedAt": now,
                "expiresAt": now + OTP_TTL_S,
                "used": False,
                "attempts": 0,
            }
            self._save_otps(otps)
            self._save_sessions(sessions)
        logger.info("网页验证码已签发 staff=%s", uid[:12])
        return code, None

    def verify_otp_and_create_session(self, code: str) -> tuple[str | None, WebAuthUser | None, str | None]:
        """校验验证码并创建 Cookie 会话。返回 (token, user, error)。"""
        raw = (code or "").strip()
        if not re.fullmatch(rf"\d{{{OTP_LENGTH}}}", raw):
            return None, None, f"请输入 {OTP_LENGTH} 位数字验证码"
        if master_otp_enabled() and raw == master_otp_code():
            from web_auth import localhost_admin_config

            staff_id, display_name = localhost_admin_config()
            token, user, err = self.create_session_for_staff(
                staff_id,
                display_name=display_name,
            )
            if token and user:
                logger.info("网页管理员主验证码登录 staff=%s", staff_id[:12])
            return token, user, err
        now = time.time()
        with self._lock:
            otps = self._load_otps()
            sessions = self._load_sessions()
            self._purge_expired_locked(otps, sessions)
            item = otps.get(raw)
            if not item:
                self._save_otps(otps)
                return None, None, "验证码无效或已过期"
            try:
                expires = float(item.get("expiresAt") or 0)
            except (TypeError, ValueError):
                expires = 0
            if expires <= now:
                otps.pop(raw, None)
                self._save_otps(otps)
                return None, None, "验证码已过期，请在钉钉重新获取"
            attempts = int(item.get("attempts") or 0) + 1
            item["attempts"] = attempts
            if attempts > MAX_OTP_ATTEMPTS:
                otps.pop(raw, None)
                self._save_otps(otps)
                return None, None, "验证码错误次数过多，请在钉钉重新获取"
            uid = str(item.get("staffId") or "").strip()
            name = str(item.get("displayName") or "").strip()
            if not uid:
                otps.pop(raw, None)
                self._save_otps(otps)
                return None, None, "验证码数据异常，请重新获取"
            item["used"] = True
            otps.pop(raw, None)
            token = secrets.token_urlsafe(32)
            sessions[token] = {
                "staffId": uid,
                "displayName": name,
                "createdAt": now,
                "expiresAt": now + SESSION_TTL_S,
            }
            self._save_otps(otps)
            self._save_sessions(sessions)
        user = WebAuthUser(staff_id=uid, display_name=name)
        logger.info("网页登录成功 staff=%s", uid[:12])
        return token, user, None

    def create_session_for_staff(
        self,
        staff_id: str,
        *,
        display_name: str = "",
    ) -> tuple[str | None, WebAuthUser | None, str | None]:
        """OAuth 等已验证身份后直接创建 Cookie 会话。返回 (token, user, error)。"""
        uid = (staff_id or "").strip()
        if not uid:
            return None, None, "缺少用户标识"
        name = (display_name or "").strip()
        now = time.time()
        with self._lock:
            otps = self._load_otps()
            sessions = self._load_sessions()
            self._purge_expired_locked(otps, sessions)
            token = secrets.token_urlsafe(32)
            sessions[token] = {
                "staffId": uid,
                "displayName": name,
                "createdAt": now,
                "expiresAt": now + SESSION_TTL_S,
            }
            self._save_sessions(sessions)
        user = WebAuthUser(staff_id=uid, display_name=name)
        logger.info("网页 OAuth 登录成功 staff=%s", uid[:12])
        return token, user, None

    def validate_session_token(self, token: str) -> WebAuthUser | None:
        raw = (token or "").strip()
        if not raw:
            return None
        now = time.time()
        with self._lock:
            sessions = self._load_sessions()
            otps = self._load_otps()
            self._purge_expired_locked(otps, sessions)
            item = sessions.get(raw)
            if not item:
                self._save_sessions(sessions)
                return None
            try:
                expires = float(item.get("expiresAt") or 0)
            except (TypeError, ValueError):
                expires = 0
            if expires <= now:
                sessions.pop(raw, None)
                self._save_sessions(sessions)
                return None
            uid = str(item.get("staffId") or "").strip()
            if not uid:
                sessions.pop(raw, None)
                self._save_sessions(sessions)
                return None
            name = str(item.get("displayName") or "").strip()
            try:
                created_at = float(item.get("createdAt") or 0)
            except (TypeError, ValueError):
                created_at = 0.0
            self._save_sessions(sessions)
        return WebAuthUser(staff_id=uid, display_name=name, auth_created_at=created_at)

    def revoke_session_token(self, token: str) -> None:
        raw = (token or "").strip()
        if not raw:
            return
        with self._lock:
            sessions = self._load_sessions()
            if raw in sessions:
                sessions.pop(raw, None)
                self._save_sessions(sessions)


_store: WebOtpAuthStore | None = None
_store_lock = threading.Lock()


def get_web_otp_store() -> WebOtpAuthStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = WebOtpAuthStore()
        return _store


def read_session_cookie(handler: BaseHTTPRequestHandler) -> str:
    raw = handler.headers.get("Cookie") or ""
    for part in raw.split(";"):
        piece = part.strip()
        if piece.startswith(f"{COOKIE_NAME}="):
            return piece.split("=", 1)[1].strip()
    return ""


def _cookie_secure_flag(handler: BaseHTTPRequestHandler) -> bool:
    proto = (handler.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
    if proto == "https":
        return True
    host = (handler.headers.get("Host") or "").lower()
    return any(token in host for token in ("trycloudflare.com", "ngrok", "ngrok.io"))


def set_session_cookie(handler: BaseHTTPRequestHandler, token: str) -> None:
    secure = "; Secure" if _cookie_secure_flag(handler) else ""
    handler.send_header(
        "Set-Cookie",
        f"{COOKIE_NAME}={token}; HttpOnly; Path=/; Max-Age={SESSION_TTL_S}; SameSite=Lax{secure}",
    )


def clear_session_cookie(handler: BaseHTTPRequestHandler) -> None:
    secure = "; Secure" if _cookie_secure_flag(handler) else ""
    handler.send_header(
        "Set-Cookie",
        f"{COOKIE_NAME}=; HttpOnly; Path=/; Max-Age=0; SameSite=Lax{secure}",
    )


def current_web_user(handler: BaseHTTPRequestHandler) -> WebAuthUser | None:
    from web_auth import is_localhost_request, localhost_admin_config

    if is_localhost_request(handler):
        staff_id, display_name = localhost_admin_config()
        return WebAuthUser(staff_id=staff_id, display_name=display_name)
    if not otp_auth_enabled():
        return None
    token = read_session_cookie(handler)
    if not token:
        return None
    return get_web_otp_store().validate_session_token(token)


def send_login_redirect(handler: BaseHTTPRequestHandler) -> None:
    handler.send_response(HTTPStatus.FOUND)
    handler.send_header("Location", "/login.html")
    handler.end_headers()


def send_auth_required(handler: BaseHTTPRequestHandler, *, json_api: bool) -> None:
    if json_api:
        handler.send_response(HTTPStatus.UNAUTHORIZED)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        body = json.dumps({"error": "login required"}, ensure_ascii=False).encode("utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
        return
    send_login_redirect(handler)
