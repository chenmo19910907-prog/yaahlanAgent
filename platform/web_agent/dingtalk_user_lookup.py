"""钉钉 userId → 姓名解析（会话内已知昵称 + 通讯录 API + 本地缓存）。"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from web_session_store import SessionMeta

logger = logging.getLogger("web-agent")

WEB_AGENT_DIR = Path(__file__).resolve().parent
NAME_CACHE_PATH = WEB_AGENT_DIR / "data" / "dingtalk_user_names.json"

_lock = threading.Lock()
_cache: dict[str, str] | None = None


def _load_cache() -> dict[str, str]:
    global _cache
    if _cache is not None:
        return _cache
    if not NAME_CACHE_PATH.is_file():
        _cache = {}
        return _cache
    try:
        raw = json.loads(NAME_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _cache = {}
        return _cache
    if not isinstance(raw, dict):
        _cache = {}
        return _cache
    _cache = {str(k): str(v) for k, v in raw.items() if str(k).strip() and str(v).strip()}
    return _cache


def _save_cache(data: dict[str, str]) -> None:
    global _cache
    NAME_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    NAME_CACHE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _cache = dict(data)


def collect_known_labels(sessions: list[SessionMeta]) -> dict[str, str]:
    """从已有会话里汇总 staffId → 钉钉昵称。"""
    known: dict[str, str] = {}
    for meta in sessions:
        if meta.source != "dingtalk":
            continue
        uid = (meta.dingtalk_owner_id or "").strip()
        label = (meta.dingtalk_label or "").strip()
        if uid and label and uid not in known:
            known[uid] = label
    return known


def _fetch_name_from_api(user_id: str) -> str | None:
    """调用钉钉通讯录 API 查询姓名（需应用开通成员信息读权限）。"""
    uid = (user_id or "").strip()
    if not uid:
        return None
    try:
        import sys

        gateway_dir = WEB_AGENT_DIR.parent / "dingtalk_gateway"
        if str(gateway_dir) not in sys.path:
            sys.path.insert(0, str(gateway_dir))
        from alidocs_upload import get_access_token  # noqa: WPS433

        token = get_access_token()
    except Exception as exc:  # noqa: BLE001
        logger.debug("获取钉钉 token 失败，跳过姓名解析 uid=%s: %s", uid[:12], exc)
        return None

    url = f"https://oapi.dingtalk.com/topapi/v2/user/get?access_token={token}"
    payload = json.dumps({"userid": uid, "language": "zh_CN"}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
        logger.debug("钉钉用户查询失败 uid=%s: %s", uid[:12], exc)
        return None

    if int(data.get("errcode") or 0) != 0:
        logger.debug(
            "钉钉用户查询 errcode=%s uid=%s",
            data.get("errcode"),
            uid[:12],
        )
        return None
    result = data.get("result")
    if not isinstance(result, dict):
        return None
    for key in ("name", "nickname", "real_authed_name"):
        value = str(result.get(key) or "").strip()
        if value:
            return value
    return None


def resolve_dingtalk_name(
    user_id: str,
    *,
    known: dict[str, str] | None = None,
    try_api: bool = True,
) -> str:
    """解析 userId 为展示名；失败则返回空字符串。"""
    uid = (user_id or "").strip()
    if not uid:
        return ""

    with _lock:
        cache = _load_cache()
        if uid in cache:
            return cache[uid]
        if known and uid in known:
            name = known[uid]
            cache[uid] = name
            _save_cache(cache)
            return name

    if try_api:
        name = _fetch_name_from_api(uid)
        if name:
            with _lock:
                cache = _load_cache()
                cache[uid] = name
                _save_cache(cache)
            return name

    if known and uid in known:
        return known[uid]
    return ""


def enrich_session_owner_labels(
    sessions: list[SessionMeta],
    *,
    try_api: bool = True,
    max_api_lookups: int = 8,
) -> int:
    """补全 dingtalk_label 为空的会话；返回更新条数。"""
    known = collect_known_labels(sessions)
    with _lock:
        cache = _load_cache()
        known.update(cache)

    updated = 0
    api_calls = 0
    for meta in sessions:
        if meta.source != "dingtalk":
            continue
        if (meta.dingtalk_label or "").strip():
            continue
        uid = (meta.dingtalk_owner_id or "").strip()
        if not uid:
            continue
        name = known.get(uid, "")
        if not name and try_api and api_calls < max_api_lookups:
            name = resolve_dingtalk_name(uid, known=known, try_api=True)
            api_calls += 1
        if not name:
            continue
        meta.dingtalk_label = name
        known[uid] = name
        updated += 1

    return updated
