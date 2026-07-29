"""快捷入口 favicon 代理：从目标站点拉取 /favicon.ico，与浏览器标签页图标一致。"""

from __future__ import annotations

import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger("web-agent")

_USER_AGENT = "YaahlanWebAgent/1.0"
_MAX_BYTES = 256 * 1024
_TIMEOUT_S = 8


def normalize_page_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        return f"https:{url}"
    if not url.startswith(("http://", "https://")):
        return f"https://{url}"
    return url


def favicon_candidates(page_url: str) -> list[str]:
    base = normalize_page_url(page_url)
    if not base:
        return []
    parsed = urlparse(base)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return []
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return [
        urljoin(origin, "/favicon.ico"),
        urljoin(origin, "/apple-touch-icon.png"),
    ]


def _looks_like_image(content_type: str, candidate_url: str, data: bytes) -> bool:
    ctype = (content_type or "").lower()
    if "image" in ctype or "icon" in ctype:
        return True
    if candidate_url.endswith(".ico") and data[:4] in (b"\x00\x00\x01\x00", b"\x00\x00\x02\x00"):
        return True
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:3] == b"GIF":
        return True
    if data[:2] == b"\xff\xd8":
        return True
    return False


def fetch_favicon(page_url: str) -> tuple[bytes, str] | None:
    """按候选顺序拉取 favicon；成功返回 (bytes, content_type)。"""
    for candidate in favicon_candidates(page_url):
        try:
            req = Request(candidate, headers={"User-Agent": _USER_AGENT})
            with urlopen(req, timeout=_TIMEOUT_S) as resp:
                data = resp.read(_MAX_BYTES + 1)
                if len(data) > _MAX_BYTES or len(data) < 32:
                    continue
                ctype = resp.headers.get_content_type() or "image/x-icon"
                if not _looks_like_image(ctype, candidate, data):
                    continue
                return data, ctype
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            logger.debug("favicon miss %s: %s", candidate, exc)
            continue
    return None
