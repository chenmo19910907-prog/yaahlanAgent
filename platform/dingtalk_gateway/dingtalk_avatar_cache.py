"""钉钉用户头像本地磁盘缓存 — Web Agent 从本地读取，避免每次刷新拉 CDN。"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from env_loader import GATEWAY_DIR

logger = logging.getLogger("dingtalk-gateway")

AVATAR_CACHE_DIR = GATEWAY_DIR / "data" / "avatar_cache"
MAX_AVATAR_BYTES = 5 * 1024 * 1024
_STAFF_ID_RE = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")

_lock = threading.Lock()
_refresh_lock = threading.Lock()
_refresh_last_attempt: dict[str, float] = {}
_refresh_inflight: set[str] = set()
DEFAULT_AVATAR_REFRESH_DEBOUNCE_SEC = 300


def normalize_staff_id(staff_id: str) -> str:
    sid = (staff_id or "").strip()
    if not sid or not _STAFF_ID_RE.fullmatch(sid):
        return ""
    return sid


def local_avatar_url(staff_id: str, *, version: int = 0) -> str:
    sid = normalize_staff_id(staff_id)
    if not sid:
        return ""
    base = f"/api/dingtalk/avatar/{urllib.parse.quote(sid, safe='')}"
    if version > 0:
        return f"{base}?v={version}"
    return base


def _meta_path(staff_id: str) -> Path:
    return AVATAR_CACHE_DIR / f"{staff_id}.meta.json"


def _guess_ext(content_type: str, url: str) -> str:
    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    mapping = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    if ctype in mapping:
        return mapping[ctype]
    lowered = (url or "").lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if lowered.endswith(ext):
            return ext if ext != ".jpeg" else ".jpg"
    return ".jpg"


def _load_meta(staff_id: str) -> dict[str, str]:
    path = _meta_path(staff_id)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def _save_meta(staff_id: str, meta: dict[str, str]) -> None:
    AVATAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _meta_path(staff_id).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _purge_avatar_cache(staff_id: str) -> None:
    sid = normalize_staff_id(staff_id)
    if not sid:
        return
    with _lock:
        for old in AVATAR_CACHE_DIR.glob(f"{sid}.*"):
            try:
                old.unlink()
            except OSError:
                pass


def _is_placeholder_avatar_image(data: bytes, content_type: str = "") -> bool:
    """钉钉默认头像多为半透明 PNG 线框，小尺寸下等同「无头像」。"""
    if not data:
        return True
    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    if ctype == "image/jpeg" or data[:3] == b"\xff\xd8\xff":
        return False
    try:
        from PIL import Image  # noqa: WPS433
        import io

        img = Image.open(io.BytesIO(data)).convert("RGBA")
        total = img.size[0] * img.size[1]
        if total <= 0:
            return True
        opaque = sum(1 for _r, _g, _b, alpha in img.getdata() if alpha > 128)
        return (opaque / total) < 0.15
    except ImportError:
        logger.debug("Pillow 未安装，跳过占位头像检测")
        return False
    except Exception as exc:  # noqa: BLE001
        logger.debug("占位头像检测失败: %s", exc)
        return False


def _download_avatar(source_url: str) -> tuple[bytes, str] | None:
    url = (source_url or "").strip()
    if not url:
        return None
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            content_type = str(resp.headers.get("Content-Type") or "")
            data = resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        logger.debug("下载头像失败: %s", exc)
        return None
    if not data or len(data) > MAX_AVATAR_BYTES:
        if len(data) > MAX_AVATAR_BYTES:
            logger.warning("头像过大，跳过缓存 (%s bytes)", len(data))
        return None
    return data, content_type


def ensure_avatar_cached(staff_id: str, source_url: str) -> Path | None:
    """确保 staffId 对应头像已落盘；source_url 变化时重新下载。"""
    sid = normalize_staff_id(staff_id)
    url = (source_url or "").strip()
    if not sid or not url:
        return None

    with _lock:
        meta = _load_meta(sid)
        ext = meta.get("ext") or ".jpg"
        file_path = AVATAR_CACHE_DIR / f"{sid}{ext}"
        cached_url = (meta.get("sourceUrl") or "").strip()
        if file_path.is_file() and cached_url == url:
            try:
                cached_data = file_path.read_bytes()
            except OSError:
                cached_data = b""
            if not _is_placeholder_avatar_image(cached_data, meta.get("contentType") or ""):
                return file_path
            _purge_avatar_cache(sid)

    payload = _download_avatar(url)
    if payload is None:
        with _lock:
            if file_path.is_file() and cached_url:
                try:
                    stale = file_path.read_bytes()
                except OSError:
                    stale = b""
                if not _is_placeholder_avatar_image(stale, meta.get("contentType") or ""):
                    return file_path
        return None

    data, content_type = payload
    if _is_placeholder_avatar_image(data, content_type):
        logger.debug("跳过钉钉默认占位头像 uid=%s", sid[:12])
        return None
    ext = _guess_ext(content_type, url)
    file_path = AVATAR_CACHE_DIR / f"{sid}{ext}"

    with _lock:
        AVATAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        for old in AVATAR_CACHE_DIR.glob(f"{sid}.*"):
            if old.name.endswith(".meta.json"):
                continue
            if old != file_path:
                try:
                    old.unlink()
                except OSError:
                    pass
        file_path.write_bytes(data)
        _save_meta(
            sid,
            {
                "sourceUrl": url,
                "ext": ext,
                "contentType": content_type.split(";", 1)[0].strip() or "image/jpeg",
            },
        )
    return file_path


def get_cached_avatar_file(staff_id: str) -> tuple[Path, str] | None:
    """读取已缓存头像；返回 (path, content_type)。"""
    sid = normalize_staff_id(staff_id)
    if not sid:
        return None
    meta = _load_meta(sid)
    ext = meta.get("ext") or ".jpg"
    file_path = AVATAR_CACHE_DIR / f"{sid}{ext}"
    if not file_path.is_file():
        return None
    ctype = meta.get("contentType") or "image/jpeg"
    try:
        data = file_path.read_bytes()
    except OSError:
        return None
    if _is_placeholder_avatar_image(data, ctype):
        _purge_avatar_cache(sid)
        return None
    return file_path, ctype


def avatar_refresh_debounce_sec() -> int:
    raw = os.environ.get("DINGTALK_AVATAR_REFRESH_DEBOUNCE_SEC", "").strip()
    if not raw:
        return DEFAULT_AVATAR_REFRESH_DEBOUNCE_SEC
    try:
        return max(60, int(raw))
    except ValueError:
        return DEFAULT_AVATAR_REFRESH_DEBOUNCE_SEC


def _refresh_avatar_cache_worker(staff_id: str, known_name: str) -> None:
    try:
        from dingtalk_user_profile import refresh_user_avatar_cache

        refresh_user_avatar_cache(staff_id, known_name=known_name)
    except Exception as exc:  # noqa: BLE001
        logger.debug("刷新头像缓存失败 uid=%s: %s", staff_id[:12], exc)
    finally:
        with _refresh_lock:
            _refresh_inflight.discard(staff_id)


def touch_avatar_cache(
    staff_id: str,
    *,
    known_name: str = "",
    background: bool = True,
) -> None:
    """用户活跃时后台刷新 profile + 头像文件（去重 + 防抖）。"""
    sid = normalize_staff_id(staff_id)
    if not sid:
        return
    now = time.time()
    with _refresh_lock:
        last = _refresh_last_attempt.get(sid, 0.0)
        if now - last < avatar_refresh_debounce_sec():
            return
        if sid in _refresh_inflight:
            return
        _refresh_inflight.add(sid)
        _refresh_last_attempt[sid] = now
    if background:
        threading.Thread(
            target=_refresh_avatar_cache_worker,
            args=(sid, known_name),
            daemon=True,
        ).start()
    else:
        _refresh_avatar_cache_worker(sid, known_name)


def resolve_avatar_file(staff_id: str, *, try_api: bool = True) -> tuple[Path, str] | None:
    """解析并返回本地头像文件；必要时调通讯录 API 后下载。"""
    sid = normalize_staff_id(staff_id)
    if not sid:
        return None

    from dingtalk_user_profile import resolve_user_profile

    profile = resolve_user_profile(sid, try_api=try_api)
    avatar_url = (profile.avatar_url or "").strip()
    if avatar_url:
        meta = _load_meta(sid)
        cached_url = (meta.get("sourceUrl") or "").strip()
        cached = get_cached_avatar_file(sid)
        if cached is None or cached_url != avatar_url:
            path = ensure_avatar_cached(sid, avatar_url)
            if path is not None:
                ctype = _load_meta(sid).get("contentType") or "image/jpeg"
                return path, ctype

    cached = get_cached_avatar_file(sid)
    if cached is not None:
        return cached
    if not avatar_url:
        return None
    path = ensure_avatar_cached(sid, avatar_url)
    if path is None:
        return None
    meta = _load_meta(sid)
    ctype = meta.get("contentType") or "image/jpeg"
    return path, ctype


def local_avatar_url_for_staff(staff_id: str, source_url: str = "") -> str:
    """有头像资料时返回本地代理 URL（列表接口用，不阻塞下载）。"""
    sid = normalize_staff_id(staff_id)
    url = (source_url or "").strip()
    if not sid or not url:
        cached = get_cached_avatar_file(sid)
        if cached is None:
            return ""
        path, _ = cached
        version = int(path.stat().st_mtime)
        return local_avatar_url(sid, version=version)
    cached = get_cached_avatar_file(sid)
    if cached is not None:
        meta = _load_meta(sid)
        if (meta.get("sourceUrl") or "").strip() == url:
            version = int(cached[0].stat().st_mtime)
            return local_avatar_url(sid, version=version)
    return ""
