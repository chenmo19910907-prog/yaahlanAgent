"""Web Agent 聊天附件与 Agent 回传文件：校验、落盘与读取。"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import mimetypes
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("web-agent")

WEB_AGENT_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = WEB_AGENT_DIR / "data" / "uploads"
OUTPUTS_DIR = WEB_AGENT_DIR / "data" / "outputs"

MAX_ATTACHMENTS_PER_MESSAGE = 5
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_FILE_BYTES = 15 * 1024 * 1024

MIME_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "text/markdown": ".md",
    "application/json": ".json",
    "application/pdf": ".pdf",
    "application/zip": ".zip",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/html": ".html",
    "application/xml": ".xml",
    "text/xml": ".xml",
}

EXT_MIME = {ext: mime for mime, ext in MIME_EXT.items()}

ALLOWED_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".txt",
        ".csv",
        ".md",
        ".json",
        ".pdf",
        ".zip",
        ".xlsx",
        ".xls",
        ".docx",
        ".html",
        ".xml",
    }
)

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9._-]+$")
_SAFE_ORIGINAL = re.compile(r"[^a-zA-Z0-9._\-()\u4e00-\u9fff\s]+")


class FileUploadError(ValueError):
    """附件上传校验失败。"""


# 兼容旧名
ImageUploadError = FileUploadError


@dataclass(frozen=True)
class StoredAttachment:
    api_path: str
    stored_name: str
    original_name: str
    mime: str
    size: int
    kind: str  # image | file

    def to_message_dict(self) -> dict[str, object]:
        return {
            "url": self.api_path,
            "name": self.original_name,
            "mime": self.mime,
            "size": self.size,
            "kind": self.kind,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode_payload(data_base64: str) -> bytes:
    raw = (data_base64 or "").strip()
    if not raw:
        raise FileUploadError("文件数据为空")
    if raw.startswith("data:"):
        comma = raw.find(",")
        if comma < 0:
            raise FileUploadError("文件 data URL 格式无效")
        raw = raw[comma + 1 :]
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise FileUploadError("文件 base64 解码失败") from exc


def _sanitize_original_name(name: str) -> str:
    base = Path((name or "").strip()).name
    if not base or base in (".", ".."):
        return "file"
    cleaned = _SAFE_ORIGINAL.sub("_", base).strip("._ ")
    return cleaned or "file"


def _extension_from_name(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext == ".jpeg":
        return ".jpg"
    return ext


def _normalize_image_mime(mime: str, content: bytes) -> str:
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
    raise FileUploadError(f"不支持的图片类型: {mime or 'unknown'}")


def _normalize_file_mime(mime: str, original_name: str, content: bytes) -> tuple[str, str]:
    ext = _extension_from_name(original_name)
    if ext not in ALLOWED_EXTENSIONS:
        raise FileUploadError(f"不支持的文件类型: {original_name}")
    value = (mime or "").split(";", 1)[0].strip().lower()
    if value in MIME_EXT and MIME_EXT[value] == ext:
        return value, ext
    guessed = mimetypes.guess_type(original_name)[0]
    if guessed:
        guessed = guessed.split(";", 1)[0].strip().lower()
    if guessed in MIME_EXT and MIME_EXT[guessed] == ext:
        return guessed, ext
    fallback = EXT_MIME.get(ext)
    if fallback:
        return fallback, ext
    if ext in IMAGE_EXTENSIONS:
        return _normalize_image_mime(mime, content), ext
    raise FileUploadError(f"无法识别文件类型: {original_name}")


def upload_api_path(session_id: str, filename: str) -> str:
    return f"/api/uploads/{session_id}/{filename}"


def output_api_path(session_id: str, filename: str) -> str:
    return f"/api/outputs/{session_id}/{filename}"


def _write_attachment(
    session_id: str,
    *,
    original_name: str,
    mime: str,
    content: bytes,
    kind: str,
) -> StoredAttachment:
    sid = (session_id or "").strip()
    if not sid:
        raise FileUploadError("session_id 无效")
    ext = MIME_EXT.get(mime) or _extension_from_name(original_name)
    stored_name = f"{uuid.uuid4().hex[:16]}{ext}"
    session_dir = UPLOADS_DIR / sid
    session_dir.mkdir(parents=True, exist_ok=True)
    target = session_dir / stored_name
    target.write_bytes(content)
    logger.info(
        "Web chat attachment saved session=%s kind=%s file=%s bytes=%d",
        sid,
        kind,
        stored_name,
        len(content),
    )
    return StoredAttachment(
        api_path=upload_api_path(sid, stored_name),
        stored_name=stored_name,
        original_name=original_name,
        mime=mime,
        size=len(content),
        kind=kind,
    )


def save_chat_images(session_id: str, items: list[dict[str, str]]) -> list[str]:
    """保存前端上传的图片，返回 API 访问路径列表（兼容旧接口）。"""
    attachments = save_chat_attachments(session_id, items)
    return [item.api_path for item in attachments if item.kind == "image"]


def save_chat_attachments(session_id: str, items: list[dict[str, str]]) -> list[StoredAttachment]:
    """保存前端上传的附件（图片 + 普通文件）。"""
    if not items:
        return []
    if len(items) > MAX_ATTACHMENTS_PER_MESSAGE:
        raise FileUploadError(f"最多上传 {MAX_ATTACHMENTS_PER_MESSAGE} 个附件")

    saved: list[StoredAttachment] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise FileUploadError(f"第 {index} 个附件格式无效")
        original_name = _sanitize_original_name(str(item.get("name") or f"file-{index}"))
        content = _decode_payload(str(item.get("data_base64") or ""))
        ext = _extension_from_name(original_name)
        if ext in IMAGE_EXTENSIONS:
            if len(content) > MAX_IMAGE_BYTES:
                raise FileUploadError(
                    f"第 {index} 张图片超过 {MAX_IMAGE_BYTES // (1024 * 1024)}MB 限制"
                )
            mime = _normalize_image_mime(str(item.get("mime") or ""), content)
            saved.append(
                _write_attachment(
                    session_id,
                    original_name=original_name,
                    mime=mime,
                    content=content,
                    kind="image",
                )
            )
            continue
        if len(content) > MAX_FILE_BYTES:
            raise FileUploadError(
                f"第 {index} 个文件超过 {MAX_FILE_BYTES // (1024 * 1024)}MB 限制"
            )
        mime, _ = _normalize_file_mime(str(item.get("mime") or ""), original_name, content)
        saved.append(
            _write_attachment(
                session_id,
                original_name=original_name,
                mime=mime,
                content=content,
                kind="file",
            )
        )
    return saved


def resolve_upload_file(session_id: str, filename: str) -> Path | None:
    return _resolve_file(UPLOADS_DIR, session_id, filename)


def resolve_output_file(session_id: str, filename: str) -> Path | None:
    return _resolve_file(OUTPUTS_DIR, session_id, filename)


def _resolve_file(root: Path, session_id: str, filename: str) -> Path | None:
    sid = (session_id or "").strip()
    name = (filename or "").strip()
    if not sid or not name or not _SAFE_NAME.match(name):
        return None
    path = (root / sid / name).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def local_path_from_api_path(api_path: str) -> Path | None:
    for prefix, root in (
        ("/api/uploads/", UPLOADS_DIR),
        ("/api/outputs/", OUTPUTS_DIR),
    ):
        value = (api_path or "").strip()
        if not value.startswith(prefix):
            continue
        rest = value[len(prefix) :]
        parts = rest.split("/", 1)
        if len(parts) != 2:
            return None
        return _resolve_file(root, parts[0], parts[1])
    return None


def content_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".jpeg":
        suffix = ".jpg"
    return EXT_MIME.get(suffix) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _manifest_path(session_id: str) -> Path:
    return OUTPUTS_DIR / session_id / "manifest.json"


def register_output_file(
    session_id: str,
    source_path: str | Path,
    *,
    display_name: str | None = None,
) -> StoredAttachment:
    """Agent 回传文件：复制到会话 outputs 并登记 manifest。"""
    sid = (session_id or "").strip()
    if not sid:
        raise FileUploadError("session_id 无效")
    src = Path(source_path).expanduser().resolve()
    if not src.is_file():
        raise FileUploadError(f"文件不存在: {src}")

    original_name = _sanitize_original_name(display_name or src.name)
    ext = _extension_from_name(original_name)
    if ext not in ALLOWED_EXTENSIONS:
        raise FileUploadError(f"不支持的回传文件类型: {original_name}")

    size = src.stat().st_size
    if ext in IMAGE_EXTENSIONS:
        if size > MAX_IMAGE_BYTES:
            raise FileUploadError(f"图片超过 {MAX_IMAGE_BYTES // (1024 * 1024)}MB 限制")
    elif size > MAX_FILE_BYTES:
        raise FileUploadError(f"文件超过 {MAX_FILE_BYTES // (1024 * 1024)}MB 限制")

    content = src.read_bytes()
    mime, _ = _normalize_file_mime("", original_name, content)
    stored_name = f"{uuid.uuid4().hex[:16]}{ext}"
    out_dir = OUTPUTS_DIR / sid
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / stored_name
    shutil.copy2(src, target)
    (out_dir / f"{stored_name}.name").write_text(original_name, encoding="utf-8")

    attachment = StoredAttachment(
        api_path=output_api_path(sid, stored_name),
        stored_name=stored_name,
        original_name=original_name,
        mime=mime,
        size=size,
        kind="image" if ext in IMAGE_EXTENSIONS else "file",
    )
    _append_manifest(sid, attachment)
    logger.info(
        "Web output file registered session=%s file=%s bytes=%d",
        sid,
        stored_name,
        size,
    )
    return attachment


def _append_manifest(session_id: str, attachment: StoredAttachment) -> None:
    path = _manifest_path(session_id)
    items = _load_manifest(session_id)
    items.append(
        {
            "stored_name": attachment.stored_name,
            "original_name": attachment.original_name,
            "mime": attachment.mime,
            "size": attachment.size,
            "kind": attachment.kind,
            "at": _now_iso(),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_manifest(session_id: str) -> list[dict[str, object]]:
    path = _manifest_path(session_id)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return raw if isinstance(raw, list) else []


def consume_pending_outputs(session_id: str) -> list[StoredAttachment]:
    """读取并清空本轮 Agent 待回传的文件列表。"""
    sid = (session_id or "").strip()
    if not sid:
        return []
    path = _manifest_path(sid)
    items = _load_manifest(sid)
    if path.is_file():
        path.unlink(missing_ok=True)

    attachments: list[StoredAttachment] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        stored_name = str(item.get("stored_name") or "").strip()
        if not stored_name or not _SAFE_NAME.match(stored_name):
            continue
        file_path = resolve_output_file(sid, stored_name)
        if file_path is None:
            continue
        attachments.append(
            StoredAttachment(
                api_path=output_api_path(sid, stored_name),
                stored_name=stored_name,
                original_name=str(item.get("original_name") or stored_name),
                mime=str(item.get("mime") or content_type_for_path(file_path)),
                size=int(item.get("size") or file_path.stat().st_size),
                kind=str(item.get("kind") or "file"),
            )
        )
    return attachments


def output_display_name(session_id: str, stored_name: str) -> str | None:
    sid = (session_id or "").strip()
    name = (stored_name or "").strip()
    if not sid or not name:
        return None
    meta_path = (OUTPUTS_DIR / sid / f"{name}.name").resolve()
    try:
        meta_path.relative_to(OUTPUTS_DIR.resolve())
    except ValueError:
        return None
    if not meta_path.is_file():
        return None
    value = meta_path.read_text(encoding="utf-8").strip()
    return value or None


def parse_web_user_key(user_key: str) -> str | None:
    key = (user_key or "").strip()
    if key.startswith("web:"):
        sid = key[4:].strip()
        return sid or None
    return None
