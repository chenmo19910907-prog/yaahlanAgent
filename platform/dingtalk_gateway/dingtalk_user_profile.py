"""钉钉通讯录用户资料（姓名、头像）— 供群 @ 网关注入发送者上下文。"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from env_loader import GATEWAY_DIR

logger = logging.getLogger("dingtalk-gateway")

PROFILE_CACHE_PATH = GATEWAY_DIR / "data" / "dingtalk_user_profiles.json"
ATTACHMENTS_DIR = GATEWAY_DIR / "attachments"
MAX_AVATAR_BYTES = 5 * 1024 * 1024

AVATAR_INTENT_RE = re.compile(r"头像|avatar|相片|照片", re.I)

_lock = threading.Lock()
_cache: dict[str, dict[str, str]] | None = None


@dataclass(frozen=True)
class UserProfile:
    staff_id: str
    display_name: str
    avatar_url: str = ""


def _load_cache() -> dict[str, dict[str, str]]:
    global _cache
    if _cache is not None:
        return _cache
    if not PROFILE_CACHE_PATH.is_file():
        _cache = {}
        return _cache
    try:
        raw = json.loads(PROFILE_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _cache = {}
        return _cache
    if not isinstance(raw, dict):
        _cache = {}
        return _cache
    _cache = {
        str(k): {str(kk): str(vv) for kk, vv in val.items() if isinstance(val, dict)}
        for k, val in raw.items()
        if str(k).strip() and isinstance(val, dict)
    }
    return _cache


def _save_cache(data: dict[str, dict[str, str]]) -> None:
    global _cache
    PROFILE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_CACHE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _cache = dict(data)


def _get_access_token() -> str:
    from alidocs_upload import get_access_token

    return get_access_token()


def _fetch_profile_from_api(staff_id: str) -> UserProfile | None:
    uid = (staff_id or "").strip()
    if not uid:
        return None
    try:
        token = _get_access_token()
    except Exception as exc:  # noqa: BLE001
        logger.debug("获取钉钉 token 失败，跳过用户资料 uid=%s: %s", uid[:12], exc)
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
        logger.debug("钉钉用户资料查询失败 uid=%s: %s", uid[:12], exc)
        return None

    if int(data.get("errcode") or 0) != 0:
        logger.debug(
            "钉钉用户资料 errcode=%s uid=%s",
            data.get("errcode"),
            uid[:12],
        )
        return None
    result = data.get("result")
    if not isinstance(result, dict):
        return None

    display_name = ""
    for key in ("name", "nickname", "real_authed_name"):
        value = str(result.get(key) or "").strip()
        if value:
            display_name = value
            break
    avatar_url = str(result.get("avatar") or "").strip()
    return UserProfile(staff_id=uid, display_name=display_name, avatar_url=avatar_url)


def resolve_user_profile(
    staff_id: str,
    *,
    known_name: str = "",
    try_api: bool = True,
    force_refresh: bool = False,
) -> UserProfile:
    """解析发送者资料；优先缓存，必要时调 Contact.User.Read 对应接口。"""
    uid = (staff_id or "").strip()
    known = (known_name or "").strip()
    if not uid:
        return UserProfile(staff_id="", display_name=known)

    with _lock:
        cached = dict(_load_cache().get(uid) or {})

    display_name = known or str(cached.get("displayName") or "").strip()
    avatar_url = str(cached.get("avatarUrl") or "").strip()

    has_cache = bool(cached)
    needs_api = force_refresh or (
        try_api
        and (
            not has_cache
            or not avatar_url
            or (known and not display_name)
        )
    )
    if needs_api:
        fetched = _fetch_profile_from_api(uid)
        if fetched:
            if fetched.display_name:
                display_name = fetched.display_name
            if fetched.avatar_url:
                avatar_url = fetched.avatar_url
            with _lock:
                store = _load_cache()
                prev = dict(store.get(uid) or {})
                merged = {
                    "displayName": display_name or prev.get("displayName") or "",
                    "avatarUrl": avatar_url or prev.get("avatarUrl") or "",
                    "updatedAt": str(time.time()),
                }
                if merged != prev:
                    store[uid] = merged
                    _save_cache(store)

    return UserProfile(
        staff_id=uid,
        display_name=display_name or uid,
        avatar_url=avatar_url,
    )


def refresh_user_avatar_cache(
    staff_id: str,
    *,
    known_name: str = "",
) -> UserProfile:
    """刷新 profile 并落盘头像文件（用户活跃时调用）。"""
    profile = resolve_user_profile(
        staff_id,
        known_name=known_name,
        try_api=True,
        force_refresh=True,
    )
    if profile.avatar_url:
        from dingtalk_avatar_cache import ensure_avatar_cached

        ensure_avatar_cached(profile.staff_id, profile.avatar_url)
    return profile


def format_sender_context(profile: UserProfile) -> str:
    if not profile.staff_id:
        return ""
    lines = [f"发送者：{profile.display_name}（staffId={profile.staff_id}）"]
    if profile.avatar_url:
        lines.append(f"头像：{profile.avatar_url}")
    return "\n".join(lines)


def should_attach_sender_avatar(text: str) -> bool:
    return bool(AVATAR_INTENT_RE.search(text or ""))


def download_sender_avatar(
    avatar_url: str,
    *,
    session_id: str,
) -> Path | None:
    url = (avatar_url or "").strip()
    if not url:
        return None
    dest_dir = ATTACHMENTS_DIR / (session_id or "unknown")
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / "sender_avatar.jpg"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read()
        if len(content) > MAX_AVATAR_BYTES:
            logger.warning("发送者头像过大，跳过下载 (%s bytes)", len(content))
            return None
        path.write_bytes(content)
        return path
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        logger.debug("下载发送者头像失败: %s", exc)
        return None


def clear_profile_cache() -> None:
    global _cache
    _cache = None
