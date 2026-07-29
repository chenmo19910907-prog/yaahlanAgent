"""兼容层：旧模块名 web_image_store → web_file_store。"""

from web_file_store import (  # noqa: F401
    ALLOWED_EXTENSIONS,
    IMAGE_EXTENSIONS,
    MAX_ATTACHMENTS_PER_MESSAGE,
    MAX_FILE_BYTES,
    MAX_IMAGE_BYTES,
    FileUploadError,
    ImageUploadError,
    StoredAttachment,
    content_type_for_path,
    local_path_from_api_path,
    output_api_path,
    resolve_output_file,
    resolve_upload_file,
    save_chat_attachments,
    save_chat_images,
    upload_api_path,
)

__all__ = [
    "ALLOWED_EXTENSIONS",
    "FileUploadError",
    "ImageUploadError",
    "MAX_ATTACHMENTS_PER_MESSAGE",
    "MAX_FILE_BYTES",
    "MAX_IMAGE_BYTES",
    "StoredAttachment",
    "content_type_for_path",
    "local_path_from_api_path",
    "output_api_path",
    "resolve_output_file",
    "resolve_upload_file",
    "save_chat_attachments",
    "save_chat_images",
    "upload_api_path",
]
