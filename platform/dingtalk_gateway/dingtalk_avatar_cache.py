"""钉钉用户头像本地磁盘缓存 — Web Agent 从本地读取，避免每次刷新拉 CDN。"""

from __future__ import annotations

import base64
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
# 群消息 @ 行内头像：物理缩略图尺寸（钉钉 Markdown 不支持 CSS/width 属性）
INLINE_AVATAR_SIZE_PX = 32
INLINE_THUMB_SHAPE = "circle"
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


def _inline_thumb_path(staff_id: str) -> Path:
    return AVATAR_CACHE_DIR / f"{staff_id}_inline.jpg"


def _center_crop_square(img: "Image.Image") -> "Image.Image":
    from PIL import Image  # noqa: WPS433

    width, height = img.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    return img.crop((left, top, left + side, top + side))


def _render_circular_thumbnail(img: "Image.Image", size: int) -> "Image.Image":
    """中心裁剪 + 圆形遮罩，输出 JPEG 可用 RGB（浅灰底）。"""
    from PIL import Image, ImageDraw  # noqa: WPS433

    square = _center_crop_square(img.convert("RGBA"))
    square = square.resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    foreground = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    foreground.paste(square, (0, 0), mask=mask)
    background = Image.new("RGB", (size, size), (245, 245, 245))
    background.paste(foreground, (0, 0), foreground)
    return background


def _web_agent_port() -> int:
    cfg_path = GATEWAY_DIR.parent / "web_agent" / "config.json"
    if not cfg_path.is_file():
        return 18766
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        return int(data.get("port") or 18766)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 18766


def inline_avatar_public_base() -> str:
    """钉钉 Markdown 拉图用的 Web Agent 公网/内网基址。"""
    from env_loader import load_env_local

    load_env_local()
    for key in ("DINGTALK_INLINE_AVATAR_PUBLIC_BASE", "WEB_AGENT_PUBLIC_BASE_URL"):
        base = (os.environ.get(key) or "").strip().rstrip("/")
        if base:
            return base
    port = _web_agent_port()
    try:
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            host = sock.getsockname()[0]
            if host and not host.startswith("127."):
                return f"http://{host}:{port}"
    except OSError:
        pass
    return ""


def inline_avatar_public_url(staff_id: str, thumb_path: Path) -> str:
    base = inline_avatar_public_base()
    sid = normalize_staff_id(staff_id)
    if not base or not sid or not thumb_path.is_file():
        return ""
    version = int(thumb_path.stat().st_mtime)
    quoted = urllib.parse.quote(sid, safe="")
    return f"{base}/api/dingtalk/avatar-inline/{quoted}?v={version}"


def inline_avatar_data_uri(thumb_path: Path) -> str:
    """内嵌 base64 圆形缩略图，供钉钉 Markdown 拉图（无法访问内网 URL）。"""
    if not thumb_path.is_file():
        return ""
    payload = base64.standard_b64encode(thumb_path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{payload}"


def _ensure_source_avatar_cached(staff_id: str, *, cdn_hint: str = "") -> Path | None:
    """确保原图已落盘（meta / 通讯录 / 消息上下文 CDN）。"""
    sid = normalize_staff_id(staff_id)
    if not sid:
        return None
    cached = get_cached_avatar_file(sid)
    if cached is not None:
        return cached[0]
    meta = _load_meta(sid)
    source = (meta.get("sourceUrl") or "").strip()
    if source:
        path = ensure_avatar_cached(sid, source)
        if path is not None:
            return path
    from dingtalk_user_profile import resolve_user_profile

    profile = resolve_user_profile(sid, try_api=True)
    source = (profile.avatar_url or "").strip()
    if source:
        return ensure_avatar_cached(sid, source)
    hint = (cdn_hint or "").strip()
    if hint.startswith(("http://", "https://")):
        return ensure_avatar_cached(sid, hint)
    return None


def ensure_inline_avatar_thumbnail(
    staff_id: str,
    *,
    size: int = INLINE_AVATAR_SIZE_PX,
    cdn_hint: str = "",
) -> Path | None:
    """生成 @ 行内展示用的小尺寸圆形 JPEG（钉钉只认物理像素，不认 width 属性）。"""
    sid = normalize_staff_id(staff_id)
    if not sid:
        return None
    src_path = _ensure_source_avatar_cached(sid, cdn_hint=cdn_hint)
    if src_path is None:
        return None
    thumb_path = _inline_thumb_path(sid)
    src_mtime = str(int(src_path.stat().st_mtime))
    meta = _load_meta(sid)
    if (
        thumb_path.is_file()
        and meta.get("inlineThumbMtime") == src_mtime
        and int(meta.get("inlineThumbSize") or 0) == size
        and meta.get("inlineThumbShape") == INLINE_THUMB_SHAPE
    ):
        return thumb_path
    try:
        from PIL import Image  # noqa: WPS433
    except ImportError:
        logger.debug("Pillow 未安装，跳过 inline 头像缩略图")
        return None
    try:
        img = _render_circular_thumbnail(Image.open(src_path), size)
        AVATAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        img.save(thumb_path, format="JPEG", quality=85)
        meta["inlineThumbMtime"] = src_mtime
        meta["inlineThumbSize"] = str(size)
        meta["inlineThumbShape"] = INLINE_THUMB_SHAPE
        _save_meta(sid, meta)
        return thumb_path
    except Exception as exc:  # noqa: BLE001
        logger.debug("生成 inline 头像缩略图失败 uid=%s: %s", sid[:12], exc)
        return None


def resolve_inline_avatar_markdown_ref(
    staff_id: str,
    *,
    cdn_fallback: str | None = None,
) -> str | None:
    """返回 Markdown @ 行头像：内嵌 base64 圆形缩略图（钉钉无法拉内网 URL）。"""
    sid = normalize_staff_id(staff_id)
    if not sid:
        return None
    cdn = (cdn_fallback or "").strip()
    thumb_path = ensure_inline_avatar_thumbnail(sid, cdn_hint=cdn)
    if thumb_path is not None:
        data_uri = inline_avatar_data_uri(thumb_path)
        if data_uri:
            return data_uri
    if cdn.startswith("https://"):
        size = INLINE_AVATAR_SIZE_PX
        return (
            f'<img src="{cdn}" width="{size}" height="{size}" '
            f'style="border-radius:50%;object-fit:cover;" />'
        )
    return None


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
