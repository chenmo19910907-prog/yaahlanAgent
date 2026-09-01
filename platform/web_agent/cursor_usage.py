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
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote

from analytics_store import (
    BJ,
    MAX_USAGE_CUSTOM_DAYS,
    resolve_usage_custom_range,
    resolve_usage_range,
)
import analytics_store
from cursor_usage_daily_store import get_cursor_usage_daily_store
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
# Dashboard 明细接口单次宽区间常只返回近 ~30 天，按块拉取以覆盖完整半年窗口。
CURSOR_FETCH_CHUNK_DAYS = 28

_AUTH_HTTP_CODES = frozenset({307, 401, 403})
_today_live_cache: dict[str, tuple[str, dict[str, int]]] = {}
_today_live_cache_lock = threading.Lock()
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


def _today_key_bj() -> str:
    return analytics_store._now_bj().strftime("%Y-%m-%d")


def _iter_day_keys(start: datetime, end: datetime) -> list[str]:
    start_bj = start.astimezone(BJ).replace(hour=0, minute=0, second=0, microsecond=0)
    end_bj = end.astimezone(BJ).replace(hour=0, minute=0, second=0, microsecond=0)
    keys: list[str] = []
    cur = start_bj
    while cur <= end_bj:
        keys.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return keys


def _day_start_bj(day_key: str) -> datetime:
    return datetime.strptime(day_key, "%Y-%m-%d").replace(tzinfo=BJ)


def _day_end_ms(day_key: str, *, now_bj: datetime | None = None) -> int:
    """单日查询上界：历史日为次日 0 点；本日为当前时刻。"""
    today_key = (now_bj or datetime.now(BJ)).strftime("%Y-%m-%d")
    start = _day_start_bj(day_key)
    if day_key >= today_key:
        return _to_ms((now_bj or datetime.now(BJ)).astimezone(timezone.utc))
    next_day = start + timedelta(days=1)
    return _to_ms(next_day.astimezone(timezone.utc))


def _group_consecutive_day_keys(day_keys: list[str]) -> list[list[str]]:
    if not day_keys:
        return []
    ordered = sorted(day_keys)
    groups: list[list[str]] = [[ordered[0]]]
    for dk in ordered[1:]:
        prev = groups[-1][-1]
        prev_dt = _day_start_bj(prev)
        cur_dt = _day_start_bj(dk)
        if (cur_dt - prev_dt).days == 1:
            groups[-1].append(dk)
        else:
            groups.append([dk])
    return groups


def _split_span_chunks(
    span_days: list[str],
    *,
    max_days: int = CURSOR_FETCH_CHUNK_DAYS,
) -> list[list[str]]:
    if not span_days:
        return []
    if len(span_days) <= max_days:
        return [span_days]
    return [span_days[i : i + max_days] for i in range(0, len(span_days), max_days)]


def _zero_fill_span_days(span_days: list[str], daily_map: dict[str, Any]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for dk in span_days:
        stats = daily_map.get(dk) if isinstance(daily_map, dict) else None
        if not isinstance(stats, dict):
            stats = {}
        out[dk] = {
            "requests": int(stats.get("requests") or 0),
            "tokens": int(stats.get("tokens") or 0),
        }
    return out


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


def _event_timestamp_ms(event: dict[str, Any]) -> int | None:
    raw = event.get("timestamp")
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, str):
        text = raw.strip()
        if text.isdigit():
            return int(text)
    return None


def _day_key_from_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=BJ).strftime("%Y-%m-%d")


def _accumulate_event_daily(
    daily: dict[str, dict[str, int]],
    event: dict[str, Any],
) -> None:
    ms = _event_timestamp_ms(event)
    if ms is None:
        return
    day = _day_key_from_ms(ms)
    bucket = daily.setdefault(day, {"requests": 0, "tokens": 0})
    bucket["requests"] += 1
    bucket["tokens"] += _event_tokens(event)


def build_daily_series(
    start: datetime,
    end: datetime,
    daily_map: dict[str, dict[str, int]],
) -> list[dict[str, Any]]:
    """按北京时间补齐周期内每一天（无数据则为 0）。"""
    start_bj = start.astimezone(BJ).replace(hour=0, minute=0, second=0, microsecond=0)
    end_bj = end.astimezone(BJ).replace(hour=0, minute=0, second=0, microsecond=0)
    rows: list[dict[str, Any]] = []
    cur = start_bj
    while cur <= end_bj:
        key = cur.strftime("%Y-%m-%d")
        stats = daily_map.get(key, {"requests": 0, "tokens": 0})
        rows.append(
            {
                "date": key,
                "label": cur.strftime("%m-%d"),
                "requests": int(stats.get("requests") or 0),
                "tokens": int(stats.get("tokens") or 0),
            }
        )
        cur += timedelta(days=1)
    return rows


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
    daily: dict[str, dict[str, int]] = defaultdict(lambda: {"requests": 0, "tokens": 0})

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
            _accumulate_event_daily(daily, event)
        if len(events) < PAGE_SIZE:
            break
        if total_count and page * PAGE_SIZE >= total_count:
            break
        page += 1

    if requests == 0 and page == 1:
        requests = len(_extract_events(payload)) if "payload" in locals() else 0

    return {"requests": requests, "tokens": tokens, "daily": dict(daily)}


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
    daily: dict[str, dict[str, int]] = defaultdict(lambda: {"requests": 0, "tokens": 0})

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
            _accumulate_event_daily(daily, event)
        pagination = payload.get("pagination")
        has_next = isinstance(pagination, dict) and bool(pagination.get("hasNextPage"))
        if not has_next and len(events) < PAGE_SIZE:
            break
        if total_count and page * PAGE_SIZE >= total_count:
            break
        page += 1

    return {"requests": requests, "tokens": tokens, "daily": dict(daily)}


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


def _resolve_fetch_stats(
    *,
    session_token: str,
    cursor_email: str,
    team_id: str,
    workos_id: str,
    start_ms: int,
    end_ms: int,
) -> tuple[dict[str, Any] | None, str, str | None]:
    """返回 (stats, source, auth_error)。"""
    admin_available = _admin_api_available() and bool(cursor_email)
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
            logger.warning("Cursor Dashboard 会话失效")
        except RuntimeError as exc:
            logger.warning("Cursor Dashboard 用量查询失败: %s", exc)
            raise

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
            logger.warning("Cursor Admin 用量查询失败: %s", exc)
            if auth_error:
                return None, source, auth_error
            raise

    return stats, source, auth_error


def _fetch_and_cache_days(
    staff_id: str,
    day_keys: list[str],
    *,
    session_token: str,
    cursor_email: str,
    team_id: str,
    workos_id: str,
) -> tuple[str, str | None, dict[str, dict[str, int]]]:
    """拉取缺失自然日；仅历史日写入按日缓存，本日只返回不落库。返回 (source, auth_error, fetched)。"""
    if not day_keys:
        return "cursor_dashboard", None, {}

    store = get_cursor_usage_daily_store()
    today_key = _today_key_bj()
    store.purge_today(staff_id)
    now_bj = analytics_store._now_bj()
    source = "cursor_dashboard"
    auth_error: str | None = None
    fetched: dict[str, dict[str, int]] = {}

    for span in _group_consecutive_day_keys(day_keys):
        for chunk in _split_span_chunks(span):
            start_ms = _to_ms(_day_start_bj(chunk[0]).astimezone(timezone.utc))
            end_ms = _day_end_ms(chunk[-1], now_bj=now_bj)
            stats, span_source, span_auth = _resolve_fetch_stats(
                session_token=session_token,
                cursor_email=cursor_email,
                team_id=team_id,
                workos_id=workos_id,
                start_ms=start_ms,
                end_ms=end_ms,
            )
            if stats is None:
                if span_auth and not auth_error:
                    auth_error = span_auth
                continue
            source = span_source
            daily_map = stats.get("daily")
            if not isinstance(daily_map, dict):
                daily_map = {}
            filled = _zero_fill_span_days(chunk, daily_map)
            fetched.update(filled)
            to_store = {
                dk: stats_row
                for dk, stats_row in filled.items()
                if dk < today_key
            }
            if to_store:
                store.set_days(staff_id, to_store)

    store.trim_leading_empty_days(staff_id, *_usage_trim_window())

    return source, auth_error, fetched


def clear_user_usage_daily_cache(staff_id: str) -> None:
    get_cursor_usage_daily_store().clear_staff(staff_id)


def should_clear_usage_cache_on_credential_update(
    old_creds: dict[str, str],
    *,
    session_token: str | None = None,
    cursor_email: str | None = None,
    team_id: str | None = None,
    workos_id: str | None = None,
) -> bool:
    """换绑 Cursor 账号时清空历史按日缓存；同账号仅续期 cookie 则保留。"""
    if not old_creds.get("sessionToken") and not old_creds.get("cursorEmail"):
        return False

    new_workos = (workos_id or "").strip()
    old_workos = (old_creds.get("workosId") or "").strip()
    if new_workos and old_workos and new_workos != old_workos:
        return True

    new_team = (team_id or "").strip()
    old_team = (old_creds.get("teamId") or "").strip()
    if new_team and old_team and new_team != old_team:
        return True

    if cursor_email is not None:
        new_email = (cursor_email or "").strip().lower()
        old_email = (old_creds.get("cursorEmail") or "").strip().lower()
        if new_email and old_email and new_email != old_email:
            return True

    if session_token is not None and not new_workos and not new_team:
        old_token = (old_creds.get("sessionToken") or "").strip()
        new_token = (session_token or "").strip()
        if old_token and new_token and old_token != new_token:
            return False

    return False


def clear_user_today_live_cache(staff_id: str) -> None:
    sid = (staff_id or "").strip()
    if not sid:
        return
    with _today_live_cache_lock:
        _today_live_cache.pop(sid, None)


def _get_cached_today(staff_id: str) -> dict[str, int] | None:
    sid = (staff_id or "").strip()
    if not sid:
        return None
    today_key = _today_key_bj()
    with _today_live_cache_lock:
        entry = _today_live_cache.get(sid)
        if entry and entry[0] == today_key:
            return dict(entry[1])
    return None


def _set_cached_today(staff_id: str, stats: dict[str, int]) -> None:
    sid = (staff_id or "").strip()
    if not sid:
        return
    today_key = _today_key_bj()
    row = {
        "requests": int(stats.get("requests") or 0),
        "tokens": int(stats.get("tokens") or 0),
    }
    with _today_live_cache_lock:
        _today_live_cache[sid] = (today_key, row)


def _usage_trim_window() -> tuple[str, str]:
    today_key = _today_key_bj()
    now_bj = analytics_store._now_bj()
    since = (now_bj - timedelta(days=364)).strftime("%Y-%m-%d")
    return since, today_key


def _trim_leading_empty_usage_days(staff_id: str) -> str | None:
    sid = (staff_id or "").strip()
    if not sid:
        return None
    since, until = _usage_trim_window()
    return get_cursor_usage_daily_store().trim_leading_empty_days(sid, since, until)


def get_usage_date_bounds(staff_id: str) -> dict[str, Any]:
    """返回日期选择器边界：可选区间为近 MAX_USAGE_CUSTOM_DAYS 天，且不早于最早有用量自然日。"""
    sid = (staff_id or "").strip()
    today_key = _today_key_bj()
    now_bj = analytics_store._now_bj()
    selectable_min = (
        now_bj - timedelta(days=MAX_USAGE_CUSTOM_DAYS - 1)
    ).strftime("%Y-%m-%d")
    earliest_with_data = _trim_leading_empty_usage_days(sid) if sid else None
    effective_min = selectable_min
    if earliest_with_data and earliest_with_data > selectable_min:
        effective_min = earliest_with_data
    return {
        "minDate": effective_min,
        "maxDate": today_key,
        "earliestWithData": earliest_with_data or "",
        "preloadDays": MAX_USAGE_CUSTOM_DAYS,
    }


def summarize_user_usage(
    staff_id: str,
    *,
    range_key: str = "month",
    start_date: str = "",
    end_date: str = "",
    refresh: bool = False,
) -> dict[str, Any]:
    load_env_local()
    sid = (staff_id or "").strip()
    if (start_date or "").strip() and (end_date or "").strip():
        start, end, label, key = resolve_usage_custom_range(start_date, end_date)
    else:
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

    session_token, cursor_email, team_id, workos_id = _resolve_credentials(sid)
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

    day_keys = _iter_day_keys(start, end)
    today_key = _today_key_bj()
    daily_store = get_cursor_usage_daily_store()
    daily_store.purge_today(sid)
    _trim_leading_empty_usage_days(sid)
    if refresh:
        clear_user_today_live_cache(sid)
    to_fetch: list[str] = []
    for dk in day_keys:
        if dk == today_key:
            if refresh or _get_cached_today(sid) is None:
                to_fetch.append(dk)
        elif refresh or daily_store.get_day(sid, dk) is None:
            to_fetch.append(dk)

    source = "cursor_dashboard"
    auth_error: str | None = None
    live_fetched: dict[str, dict[str, int]] = {}
    if to_fetch:
        try:
            source, auth_error, live_fetched = _fetch_and_cache_days(
                sid,
                to_fetch,
                session_token=session_token,
                cursor_email=cursor_email,
                team_id=team_id,
                workos_id=workos_id,
            )
        except RuntimeError as exc:
            base.update(
                {
                    "error": str(exc),
                    "configured": cred_status["configured"] or has_env_session or has_env_email,
                    "needsSetup": False,
                }
            )
            return base

    daily_map: dict[str, dict[str, int]] = {}
    missing_after_fetch: list[str] = []
    for dk in day_keys:
        if dk == today_key:
            live_today = live_fetched.get(dk)
            if live_today is not None:
                daily_map[dk] = live_today
                _set_cached_today(sid, live_today)
            else:
                cached_today = _get_cached_today(sid)
                if cached_today is not None:
                    daily_map[dk] = cached_today
                else:
                    missing_after_fetch.append(dk)
            continue
        row = daily_store.get_day(sid, dk)
        if row is None:
            missing_after_fetch.append(dk)
        else:
            daily_map[dk] = row

    if missing_after_fetch and not auth_error:
        if not session_token and not admin_available:
            auth_error = auth_error or "Cursor 会话无效，请重新绑定"
        elif missing_after_fetch == [today_key] and not daily_map:
            auth_error = auth_error or "Cursor 会话无效，请重新绑定"

    if auth_error and not daily_map:
        base.update(
            {
                "error": auth_error,
                "needsReauth": True,
                "configured": cred_status["configured"] or has_env_session or has_env_email,
                "needsSetup": not (
                    cred_status["configured"] or has_env_session or has_env_email
                ),
                "adminApiAvailable": _admin_api_available(),
            }
        )
        return base

    requests = 0
    tokens = 0
    for dk in day_keys:
        stats = daily_map.get(dk, {"requests": 0, "tokens": 0})
        requests += int(stats.get("requests") or 0)
        tokens += int(stats.get("tokens") or 0)

    result = {
        **base,
        "requests": requests,
        "tokens": tokens,
        "tokensSource": "cursor" if tokens > 0 else "none",
        "source": source,
        "configured": True,
        "needsSetup": False,
        "daily": build_daily_series(start, end, daily_map),
    }
    if auth_error:
        result["error"] = auth_error
    return result
