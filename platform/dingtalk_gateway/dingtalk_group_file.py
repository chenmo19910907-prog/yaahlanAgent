"""通过 Stream 企业机器人把文件发送到当前钉钉群。"""

from __future__ import annotations

import json
import logging
import tempfile
import zipfile
from pathlib import Path

import requests
from dingtalk_stream import ChatbotHandler, ChatbotMessage
from dingtalk_stream.utils import DINGTALK_OPENAPI_ENDPOINT

logger = logging.getLogger("dingtalk-gateway")

MAX_FILE_BYTES = 20 * 1024 * 1024
_FILE_TYPE_BY_EXT = {
    "zip": "zip",
    "pdf": "pdf",
    "doc": "doc",
    "docx": "docx",
    "xlsx": "xlsx",
    "rar": "rar",
    "html": "html",
    "htm": "html",
}

_MIMETYPE_BY_EXT = {
    "html": "text/html",
    "htm": "text/html",
}


def _file_type(name: str) -> str:
    ext = Path(name).suffix.lstrip(".").lower()
    return _FILE_TYPE_BY_EXT.get(ext, ext or "zip")


def _response_succeeded(response: requests.Response) -> tuple[bool, str]:
    text = (response.text or "").strip()
    if response.status_code >= 400:
        return False, f"HTTP {response.status_code}: {text[:300]}"
    if not text:
        return True, "empty body"
    try:
        data = response.json()
    except json.JSONDecodeError:
        return True, text[:200]

    if isinstance(data, dict):
        if data.get("processQueryKey"):
            return True, str(data["processQueryKey"])
        errcode = data.get("errcode")
        if errcode is not None:
            if int(errcode) == 0:
                return True, str(data.get("errmsg") or "ok")
            return False, f"errcode={errcode}, errmsg={data.get('errmsg')}"
        code = data.get("code")
        if code and str(code).lower() not in ("ok", "success", "0"):
            return False, text[:300]
    return True, text[:200]


def _upload_file(handler: ChatbotHandler, content: bytes, filename: str) -> str:
    ext = Path(filename).suffix.lstrip(".").lower()
    mimetype = _MIMETYPE_BY_EXT.get(ext, "application/octet-stream")
    media_id = handler.dingtalk_client.upload_to_dingtalk(
        content,
        filetype="file",
        filename=filename,
        mimetype=mimetype,
    )
    if not media_id:
        raise RuntimeError(f"上传文件到钉钉失败：{filename}")
    logger.info("已上传媒体文件 %s media_id=%s…", filename, media_id[:24])
    return media_id


def _send_via_group_api(
    handler: ChatbotHandler,
    incoming: ChatbotMessage,
    *,
    media_id: str,
    filename: str,
) -> None:
    access_token = handler.dingtalk_client.get_access_token()
    if not access_token:
        raise RuntimeError("获取钉钉 access_token 失败，无法发送群文件")

    robot_code = (incoming.robot_code or "").strip()
    if not robot_code:
        robot_code = handler.dingtalk_client.credential.client_id

    file_type = _file_type(filename)
    msg_param = json.dumps(
        {
            "mediaId": media_id,
            "fileName": filename,
            "fileType": file_type,
        },
        ensure_ascii=False,
    )
    body: dict[str, str] = {
        "msgKey": "sampleFile",
        "msgParam": msg_param,
        "robotCode": robot_code,
    }
    if incoming.conversation_type == "2":
        if not incoming.conversation_id:
            raise RuntimeError("缺少 openConversationId，无法发送群文件")
        body["openConversationId"] = incoming.conversation_id
    elif incoming.conversation_type == "1":
        if not incoming.sender_staff_id:
            raise RuntimeError("缺少 sender_staff_id，无法发送单聊文件")
        body["singleChatReceiver"] = json.dumps(
            {"userId": incoming.sender_staff_id},
            ensure_ascii=False,
        )
    else:
        body["openConversationId"] = incoming.conversation_id or ""

    url = f"{DINGTALK_OPENAPI_ENDPOINT}/v1.0/robot/groupMessages/send"
    headers = {
        "Content-Type": "application/json",
        "x-acs-dingtalk-access-token": access_token,
    }
    response = requests.post(url, headers=headers, json=body, timeout=60)
    ok, detail = _response_succeeded(response)
    if not ok:
        raise RuntimeError(f"OpenAPI 发文件失败：{detail}")
    logger.info("OpenAPI 发文件成功 robot=%s detail=%s", robot_code, detail)


def _send_via_session_webhook(
    incoming: ChatbotMessage,
    *,
    media_id: str,
    filename: str,
) -> None:
    if not incoming.session_webhook:
        raise RuntimeError("缺少 sessionWebhook，无法走 Webhook 发文件")

    file_type = _file_type(filename)
    payload = {
        "msgtype": "file",
        "file": {
            "mediaId": media_id,
            "fileName": filename,
            "fileType": file_type,
        },
    }
    response = requests.post(
        incoming.session_webhook,
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=60,
    )
    ok, detail = _response_succeeded(response)
    if not ok:
        raise RuntimeError(f"sessionWebhook 发文件失败：{detail}")
    logger.info("sessionWebhook 发文件成功 detail=%s", detail)


def _zip_single_file(path: Path, *, display_name: str | None = None) -> tuple[Path, str, tempfile.TemporaryDirectory[str]]:
    """将单个非 zip 文件打成临时 zip，返回 (zip路径, 发送文件名, 临时目录)。"""
    inner_name = display_name or path.name
    zip_stem = Path(inner_name).stem or path.stem or "attachment"
    tmp_dir = tempfile.TemporaryDirectory(prefix="dingtalk-file-zip-")
    zip_path = Path(tmp_dir.name) / f"{zip_stem}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(path, arcname=inner_name)
    logger.info("非 zip 附件已自动打包 %s -> %s", path.name, zip_path.name)
    return zip_path, zip_path.name, tmp_dir


def _prepare_attachment(
    path: Path,
    *,
    display_name: str | None,
) -> tuple[Path, str, tempfile.TemporaryDirectory[str] | None]:
    """钉钉发文件须为 zip；非 zip 时自动打包。"""
    if path.suffix.lower() == ".zip":
        return path, display_name or path.name, None
    return _zip_single_file(path, display_name=display_name)


def send_group_file(
    handler: ChatbotHandler,
    incoming: ChatbotMessage,
    file_path: Path | str,
    *,
    display_name: str | None = None,
) -> None:
    """上传本地文件并发送到触发消息的会话（群/单聊）。非 zip 会自动打包为 zip。"""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(path)

    send_path, filename, tmp_dir = _prepare_attachment(path, display_name=display_name)
    try:
        content = send_path.read_bytes()
        if len(content) > MAX_FILE_BYTES:
            raise RuntimeError(
                f"文件过大（{len(content) // (1024 * 1024)}MB），钉钉单文件上限 20MB"
            )

        media_id = _upload_file(handler, content, filename)

        errors: list[str] = []
        try:
            _send_via_group_api(handler, incoming, media_id=media_id, filename=filename)
            return
        except Exception as exc:  # noqa: BLE001
            errors.append(f"OpenAPI: {exc}")
            logger.warning("OpenAPI 发文件失败，尝试 sessionWebhook：%s", exc)

        try:
            _send_via_session_webhook(incoming, media_id=media_id, filename=filename)
            return
        except Exception as exc:  # noqa: BLE001
            errors.append(f"sessionWebhook: {exc}")
            logger.error("sessionWebhook 发文件也失败：%s", exc)

        raise RuntimeError("；".join(errors))
    finally:
        if tmp_dir is not None:
            tmp_dir.cleanup()
