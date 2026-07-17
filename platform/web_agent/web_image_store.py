"""Web Agent 聊天附图：校验、落盘与读取。"""

from __future__ import annotations

import base64
import binascii
import logging
import re
import uuid
from pathlib import Path

logger = logging.getLogger("web-agent")

WEB_AGENT_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = WEB_AGENT_DIR / "data" / "uploads"

MAX_IMAGES_PER_MESSAGE = 5
MAX_IMAGE_BYTES = 5 * 1024 * 1024

MIME_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9._-]+$")


class ImageUploadError(ValueError):
    """附图上传校验失败。"""


def _decode_image_payload(data_base64: str) -> bytes:
    raw = (data_base64 or "").strip()
    if not raw:
        raise ImageUploadError("图片数据为空")
    if raw.startswith("data:"):
        comma = raw.find(",")
        if comma < 0:
            raise ImageUploadError("图片 data URL 格式无效")
        raw = raw[comma + 1 :]
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ImageUploadError("图片 base64 解码失败") from exc


def _normalize_mime(mime: str, content: bytes) -> str:
    value = (mime or "").split(";", 1)[0].strip().lower()
    if value == "image/jpg":
        value = "image/jpeg"
    if value in MIME_EXT:
        return value
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"GIF87a") or content.startswith(b"GIF89a"):
        return "image/gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    raise ImageUploadError(f"不支持的图片类型: {mime or 'unknown'}")


def upload_api_path(session_id: str, filename: str) -> str:
    return f"/api/uploads/{session_id}/{filename}"


def save_chat_images(session_id: str, items: list[dict[str, str]]) -> list[str]:
    """保存前端上传的附图，返回 API 访问路径列表。"""
    sid = (session_id or "").strip()
    if not sid:
        raise ImageUploadError("session_id 无效")
    if not items:
        return []
    if len(items) > MAX_IMAGES_PER_MESSAGE:
        raise ImageUploadError(f"最多上传 {MAX_IMAGES_PER_MESSAGE} 张图片")

    session_dir = UPLOADS_DIR / sid
    session_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ImageUploadError(f"第 {index} 张图片格式无效")
        content = _decode_image_payload(str(item.get("data_base64") or ""))
        if len(content) > MAX_IMAGE_BYTES:
            raise ImageUploadError(
                f"第 {index} 张图片超过 {MAX_IMAGE_BYTES // (1024 * 1024)}MB 限制"
            )
        mime = _normalize_mime(str(item.get("mime") or ""), content)
        ext = MIME_EXT[mime]
        filename = f"{uuid.uuid4().hex[:16]}{ext}"
        target = session_dir / filename
        target.write_bytes(content)
        paths.append(upload_api_path(sid, filename))
        logger.info("Web chat image saved session=%s file=%s bytes=%d", sid, filename, len(content))

    return paths


def resolve_upload_file(session_id: str, filename: str) -> Path | None:
    sid = (session_id or "").strip()
    name = (filename or "").strip()
    if not sid or not name or not _SAFE_NAME.match(name):
        return None
    path = (UPLOADS_DIR / sid / name).resolve()
    try:
        path.relative_to(UPLOADS_DIR.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def local_path_from_api_path(api_path: str) -> Path | None:
    prefix = "/api/uploads/"
    value = (api_path or "").strip()
    if not value.startswith(prefix):
        return None
    rest = value[len(prefix) :]
    parts = rest.split("/", 1)
    if len(parts) != 2:
        return None
    return resolve_upload_file(parts[0], parts[1])
