"""从钉钉消息下载用户附图，供 Cursor SDK 多模态调用。"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

import requests
from dingtalk_stream import ChatbotHandler

from env_loader import GATEWAY_DIR
from task_session import TaskSession

logger = logging.getLogger("dingtalk-gateway")

ATTACHMENTS_DIR = GATEWAY_DIR / "attachments"
MAX_IMAGES = 5
MAX_IMAGE_BYTES = 15 * 1024 * 1024

MIME_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def _guess_extension(content_type: str | None, download_url: str) -> str:
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime in MIME_TO_EXT:
        return MIME_TO_EXT[mime]
    guessed = mimetypes.guess_type(download_url)[0]
    if guessed in MIME_TO_EXT:
        return MIME_TO_EXT[guessed]
    return ".png"


def download_message_images(
    handler: ChatbotHandler,
    download_codes: list[str],
    *,
    session_id: str,
    session: TaskSession | None = None,
) -> list[Path]:
    if not download_codes:
        return []

    codes = download_codes[:MAX_IMAGES]
    if len(download_codes) > MAX_IMAGES:
        logger.warning("附图超过 %s 张，仅取前 %s 张", len(download_codes), MAX_IMAGES)

    dest_dir = ATTACHMENTS_DIR / (session_id or "unknown")
    dest_dir.mkdir(parents=True, exist_ok=True)

    saved: list[Path] = []
    for index, code in enumerate(codes):
        if session:
            session.check_cancelled()
        download_url = handler.get_image_download_url(code)
        if not download_url:
            raise RuntimeError(f"获取图片下载地址失败（downloadCode={code[:16]}…）")

        response = requests.get(download_url, timeout=60)
        response.raise_for_status()

        content = response.content
        if len(content) > MAX_IMAGE_BYTES:
            raise RuntimeError(
                f"图片过大（{len(content)} bytes），单张上限 {MAX_IMAGE_BYTES // (1024 * 1024)}MB"
            )

        ext = _guess_extension(response.headers.get("Content-Type"), download_url)
        path = dest_dir / f"img_{index}{ext}"
        path.write_bytes(content)
        saved.append(path)
        logger.info("已下载附图 %s (%s bytes)", path.name, len(content))

    return saved
