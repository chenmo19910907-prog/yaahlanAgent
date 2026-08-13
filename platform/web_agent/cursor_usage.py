"""从 Cursor Dashboard / Admin API 拉取个人用量。"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote

from analytics_store import resolve_usage_range
from cursor_usage_store import get_cursor_usage_store

try:
    from env_loader import load_env_local
except ImportError:
    def load_env_local() -> None:
        return None

logger = logging.getLogger("web-agent")

CURSOR_DASHBOARD_EVENTS_URL = "https://cursor.com/api/dashboard/get-filtered-usage-events"
CURSOR_ADMIN_EVENTS_URL = "https://api.cursor.com/teams/filtered-usage-events"
CURSOR_ORIGIN = "https://cursor.com"
PAGE_SIZE = 100
MAX_PAGES = 200
_CACHE_TTL_S = 300.0

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}

_AUTH_HTTP_CODES = frozenset({307, 401, 403})
_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)


class CursorAuthError(RuntimeError):
    """Cursor Dashboard 会话无效或已过期。"""


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _admin_api_available() -> bool:
    return bool(_env("CURSOR_API_KEY"))


def _cache_key(staff_id: str, range_key: str) -> str:
    return f"{staff_id}:{range_key}"


def _read_cache(staff_id: str, range_key: str) -> dict[str, Any] | None:
    key = _cache_key(staff_id, range_key)
    with _cache_lock:
        row = _cache.get(key)
    if row is None:
        return None
    expires_at, payload = row
    if time.monotonic() >= expires_at:
        with _cache_lock:
            _cache.pop(key, None)
        return None
    return payload


def _write_cache(staff_id: str, range_key: str, payload: dict[str, Any]) -> None:
    key = _cache_key(staff_id, range_key)
    with _cache_lock:
        _cache[key] = (time.monotonic() + _CACHE_TTL_S, payload)


def _to_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _event_tokens(event: dict[str, Any]) -> int:
    usage = event.get("tokenUsage")
    if not isinstance(usage, dict):
        return 0
    total = 0
    for key in ("inputTokens", "outputTokens", "cacheWriteTokens", "cacheReadTokens"):
        raw = usage.get(key)
        if isinstance(raw, (int, float)) and raw > 0:
            total += int(raw)
    return total


def _extract_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("usageEventsDisplay", "usageEvents"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _cookie_value(raw: str) -> str:
    value = (raw or "").strip()
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1].strip()
    return value


def _parse_cookie_pairs(raw: str) -> dict[str, str]:
    text = (raw or "").strip()
    if not text:
        return {}
    lowered = text.lower()
    for prefix in ("cookie:", "set-cookie:"):
        if lowered.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    pairs: dict[str, str] = {}
    for part in text.split(";"):
        chunk = part.strip()
        if not chunk or "=" not in chunk:
            continue
        name, value = chunk.split("=", 1)
        key = name.strip().lower()
        if key:
            pairs[key] = _cookie_value(value)
    return pairs


def _extract_session_token_value(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    for prefix in ("workoscursorsessiontoken=", "cookie: workoscursorsessiontoken="):
        if lowered.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    if ";" in text and "workoscursorsessiontoken" not in lowered:
        text = text.split(";", 1)[0].strip()
    return _cookie_value(text)


def parse_cursor_session_input(raw: str) -> dict[str, str]:
    """从 Token 值或整段 Cookie 文本解析 Dashboard 凭据。"""
    text = (raw or "").strip()
    if not text:
        return {"sessionToken": "", "teamId": "", "workosId": ""}

    pairs = _parse_cookie_pairs(text)
    session_token = pairs.get("workoscursorsessiontoken", "")
    team_id = pairs.get("team_id", "")
    workos_id = pairs.get("workos_id", "") or pairs.get("cursor-web-target-synced-user", "")

    if not session_token:
        session_token = _extract_session_token_value(text)

    session_token = _encode_token_for_cookie(session_token)
    if not workos_id:
        workos_id = _workos_user_id_from_token(session_token)

    return {
        "sessionToken": session_token,
        "teamId": team_id.strip(),
        "workosId": workos_id.strip(),
    }


def _normalize_session_token(raw: str) -> str:
    return parse_cursor_session_input(raw)["sessionToken"]


def _encode_token_for_cookie(token: str) -> str:
    value = (token or "").strip()
    if not value:
        return ""
    if "%3a%3a" in value.lower():
        return value
    if "::" in unquote(value):
        decoded = unquote(value)
        return decoded.replace("::", "%3A%3A")
    return value


def _workos_user_id_from_token(token: str) -> str:
    value = unquote((token or "").strip())
    if "::" in value:
        prefix = value.split("::", 1)[0].strip()
        if prefix.startswith("user_"):
            return prefix
    return ""


def _jwt_from_session_token(token: str) -> str | None:
    normalized = _normalize_session_token(token)
    if not normalized:
        return None
    decoded = unquote(normalized)
    if "::" in decoded:
        return decoded.split("::", 1)[1]
    if decoded.count(".") >= 2:
        return decoded
    return None


def _session_token_expired(token: str) -> bool:
    jwt = _jwt_from_session_token(token)
    if not jwt:
        return False
    try:
        parts = jwt.split(".")
        if len(parts) < 2:
            return False
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
        exp = payload.get("exp")
        if isinstance(exp, (int, float)):
            return time.time() >= float(exp)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    return False


def _auth_error_message(code: int) -> str:
    if code == 307:
        return (
            "Cursor 会话已过期，请打开 cursor.com/dashboard/usage 登录后，"
            "重新复制 WorkosCursorSessionToken 并保存。"
        )
    return "Cursor 会话无效，请重新绑定 WorkosCursorSessionToken。"


def _dashboard_cookie_header(
    session_token: str,
    *,
    team_id: str = "",
    workos_id: str = "",
) -> str:
    token = _encode_token_for_cookie(_normalize_session_token(session_token))
    if not token:
        return ""
    cookies = [f"WorkosCursorSessionToken={token}"]
    resolved_workos = (workos_id or _workos_user_id_from_token(token)).strip()
    if resolved_workos:
        cookies.append(f"workos_id={resolved_workos}")
        cookies.append(f"cursor-web-target-synced-user={resolved_workos}")
    if team_id.strip():
        cookies.append(f"team_id={team_id.strip()}")
    return "; ".join(cookies)


def _dashboard_headers(
    session_token: str,
    *,
    referer: str,
    team_id: str = "",
    workos_id: str = "",
) -> dict[str, str]:
    cookie = _dashboard_cookie_header(
        session_token,
        team_id=team_id,
        workos_id=workos_id,
    )
    return {
        "Cookie": cookie,
        "Origin": CURSOR_ORIGIN,
        "Referer": referer,
        "Accept": "application/json",
        "Accept-Language": "zh-CN,zh-Hans;q=0.9,en;q=0.8",
        "User-Agent": _DEFAULT_UA,
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
    }


def _http_json(
    *,
    url: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    data = None
    req_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req_headers.setdefault("Accept", "application/json")
    req_headers.setdefault("User-Agent", _DEFAULT_UA)
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final_url = resp.geturl()
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code in _AUTH_HTTP_CODES:
            raise CursorAuthError(_auth_error_message(exc.code)) from exc
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Cursor 用量接口 HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cursor 用量接口网络错误: {exc.reason}") from exc
    if "authenticator.cursor.com" in final_url or "workos.com" in final_url:
        raise CursorAuthError(_auth_error_message(307))
    if raw.lstrip().startswith("<!DOCTYPE") or raw.lstrip().startswith("<html"):
        raise CursorAuthError(_auth_error_message(307))
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CursorAuthError(_auth_error_message(307)) from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Cursor 用量接口返回格式异常")
    return parsed


def _fetch_dashboard_usage(
    session_token: str,
    *,
    start_ms: int,
    end_ms: int,
    team_id: str = "",
    workos_id: str = "",
) -> dict[str, Any]:
    token = _normalize_session_token(session_token)
    if not token:
        raise RuntimeError("缺少 Cursor 会话凭据")
    if _session_token_expired(token):
        raise CursorAuthError(_auth_error_message(307))

    start_day = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    end_day = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    referer = (
        "https://cursor.com/dashboard/usage"
        f"?startDate={start_day}&endDate={end_day}"
        f"&from={start_day}&to={end_day}"
    )
    headers = _dashboard_headers(
        token,
        referer=referer,
        team_id=team_id,
        workos_id=workos_id,
    )
    requests = 0
    tokens = 0
    page = 1
    total_count = 0

    while page <= MAX_PAGES:
        body: dict[str, Any] = {
            "startDate": str(start_ms),
            "endDate": str(end_ms),
            "page": page,
            "pageSize": PAGE_SIZE,
        }
        if team_id.strip().isdigit():
            body["teamId"] = int(team_id.strip())
        payload = _http_json(
            url=CURSOR_DASHBOARD_EVENTS_URL,
            method="POST",
            body=body,
            headers=headers,
        )
        if page == 1:
            raw_total = payload.get("totalUsageEventsCount")
            if isinstance(raw_total, (int, float)) and raw_total >= 0:
                total_count = int(raw_total)
                requests = total_count
        events = _extract_events(payload)
        if not events:
            break
        for event in events:
            tokens += _event_tokens(event)
        if len(events) < PAGE_SIZE:
            break
        if total_count and page * PAGE_SIZE >= total_count:
            break
        page += 1

    if requests == 0 and page == 1:
        requests = len(_extract_events(payload)) if "payload" in locals() else 0

    return {"requests": requests, "tokens": tokens}


def _fetch_admin_usage(
    api_key: str,
    *,
    email: str,
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    key = (api_key or "").strip()
    addr = (email or "").strip().lower()
    if not key:
        raise RuntimeError("服务端未配置 CURSOR_API_KEY")
    if not addr or "@" not in addr:
        raise RuntimeError("缺少 Cursor 登录邮箱")

    auth = base64.b64encode(f"{key}:".encode("utf-8")).decode("ascii")
    headers = {"Authorization": f"Basic {auth}"}
    requests = 0
    tokens = 0
    page = 1
    total_count = 0

    while page <= MAX_PAGES:
        payload = _http_json(
            url=CURSOR_ADMIN_EVENTS_URL,
            method="POST",
            body={
                "startDate": start_ms,
                "endDate": end_ms,
                "email": addr,
                "page": page,
                "pageSize": PAGE_SIZE,
            },
            headers=headers,
        )
        if page == 1:
            raw_total = payload.get("totalUsageEventsCount")
            if isinstance(raw_total, (int, float)) and raw_total >= 0:
                total_count = int(raw_total)
                requests = total_count
        events = _extract_events(payload)
        if not events:
            break
        for event in events:
            tokens += _event_tokens(event)
        pagination = payload.get("pagination")
        has_next = isinstance(pagination, dict) and bool(pagination.get("hasNextPage"))
        if not has_next and len(events) < PAGE_SIZE:
            break
        if total_count and page * PAGE_SIZE >= total_count:
            break
        page += 1

    return {"requests": requests, "tokens": tokens}


def _resolve_credentials(staff_id: str) -> tuple[str, str, str, str]:
    creds = get_cursor_usage_store().get_credentials(staff_id)
    session_token = _normalize_session_token(
        creds["sessionToken"] or _env("CURSOR_SESSION_TOKEN")
    )
    cursor_email = (creds["cursorEmail"] or _env("CURSOR_USAGE_EMAIL")).strip().lower()
    team_id = (creds.get("teamId") or _env("CURSOR_TEAM_ID")).strip()
    workos_id = (creds.get("workosId") or "").strip()
    if not workos_id and session_token:
        workos_id = _workos_user_id_from_token(session_token)
    return session_token, cursor_email, team_id, workos_id


def verify_session_token(
    session_token: str,
    *,
    team_id: str = "",
    workos_id: str = "",
) -> None:
    """保存前校验 Dashboard 会话是否可用。"""
    token = _normalize_session_token(session_token)
    if not token:
        raise ValueError("Session Token 不能为空")
    if _session_token_expired(token):
        raise ValueError("Session Token 已过期，请重新登录 Cursor Dashboard 后复制")
    _http_json(
        url="https://cursor.com/api/usage-summary",
        method="GET",
        headers=_dashboard_headers(
            token,
            referer="https://cursor.com/dashboard/usage",
            team_id=team_id,
            workos_id=workos_id,
        ),
        timeout=20.0,
    )


def dashboard_usage_url(start: datetime, end: datetime) -> str:
    start_day = start.astimezone(timezone.utc).strftime("%Y-%m-%d")
    end_day = end.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return (
        "https://cursor.com/dashboard/usage"
        f"?startDate={start_day}&endDate={end_day}"
        f"&from={start_day}&to={end_day}"
    )


def summarize_user_usage(staff_id: str, *, range_key: str = "month") -> dict[str, Any]:
    load_env_local()
    sid = (staff_id or "").strip()
    start, end, label, key = resolve_usage_range(range_key)
    base = {
        "range": key,
        "rangeLabel": label,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "requests": 0,
        "tokens": 0,
        "tokensSource": "none",
        "source": "cursor_dashboard",
        "dashboardUrl": dashboard_usage_url(start, end),
        "adminApiAvailable": _admin_api_available(),
    }
    if not sid:
        base["error"] = "未登录"
        return base

    cached = _read_cache(sid, key)
    if cached is not None:
        return cached

    session_token, cursor_email, team_id, workos_id = _resolve_credentials(sid)
    start_ms = _to_ms(start)
    end_ms = _to_ms(end)
    cred_status = get_cursor_usage_store().status_for_staff(sid)
    has_env_session = bool(_env("CURSOR_SESSION_TOKEN"))
    has_env_email = bool(_env("CURSOR_USAGE_EMAIL"))
    admin_available = _admin_api_available() and bool(cursor_email)

    if not session_token and not admin_available:
        base.update(
            {
                "needsSetup": True,
                "configured": False,
                "setupHint": (
                    "请绑定 Cursor 账号：在 cursor.com/dashboard/usage 登录后，"
                    "复制 Cookie「WorkosCursorSessionToken」；"
                    "或填写 Cursor 登录邮箱（需服务端配置 CURSOR_API_KEY）。"
                ),
            }
        )
        return base

    stats: dict[str, Any] | None = None
    source = "cursor_dashboard"
    auth_error: str | None = None

    if session_token:
        try:
            stats = _fetch_dashboard_usage(
                session_token,
                start_ms=start_ms,
                end_ms=end_ms,
                team_id=team_id,
                workos_id=workos_id,
            )
            source = "cursor_dashboard"
        except CursorAuthError as exc:
            auth_error = str(exc)
            logger.warning("Cursor Dashboard 会话失效 staff=%s", sid[:12])
        except RuntimeError as exc:
            logger.warning("Cursor Dashboard 用量查询失败 staff=%s: %s", sid[:12], exc)
            base.update(
                {
                    "error": str(exc),
                    "configured": cred_status["configured"] or has_env_session or has_env_email,
                    "needsSetup": False,
                }
            )
            return base

    if stats is None and admin_available:
        try:
            stats = _fetch_admin_usage(
                _env("CURSOR_API_KEY"),
                email=cursor_email,
                start_ms=start_ms,
                end_ms=end_ms,
            )
            source = "cursor_admin_api"
            auth_error = None
        except RuntimeError as exc:
            logger.warning("Cursor Admin 用量查询失败 staff=%s: %s", sid[:12], exc)
            if auth_error:
                base.update(
                    {
                        "error": auth_error,
                        "needsReauth": True,
                        "configured": True,
                        "needsSetup": False,
                        "adminApiAvailable": _admin_api_available(),
                    }
                )
                return base
            base.update(
                {
                    "error": str(exc),
                    "configured": cred_status["configured"] or has_env_session or has_env_email,
                    "needsSetup": False,
                }
            )
            return base

    if stats is None:
        base.update(
            {
                "error": auth_error or "Cursor 会话无效，请重新绑定",
                "needsReauth": bool(auth_error),
                "configured": cred_status["configured"] or has_env_session or has_env_email,
                "needsSetup": not (
                    cred_status["configured"] or has_env_session or has_env_email
                ),
                "adminApiAvailable": _admin_api_available(),
            }
        )
        return base

    result = {
        **base,
        "requests": int(stats.get("requests") or 0),
        "tokens": int(stats.get("tokens") or 0),
        "tokensSource": "cursor" if int(stats.get("tokens") or 0) > 0 else "none",
        "source": source,
        "configured": True,
        "needsSetup": False,
    }
    _write_cache(sid, key, result)
    return result
