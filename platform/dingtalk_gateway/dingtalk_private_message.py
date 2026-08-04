"""钉钉机器人私聊文本消息（OpenAPI robot/oToMessages/batchSend）。"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests
from dingtalk_stream.utils import DINGTALK_OPENAPI_ENDPOINT

from dingtalk_group_file import _response_succeeded
from env_loader import load_env_local, require_env

logger = logging.getLogger("dingtalk-gateway")


def _get_access_token(client: Any | None) -> str | None:
    if client is not None:
        token = client.get_access_token()
        if token:
            return token
    try:
        from dingtalk_stream import Credential, DingTalkStreamClient

        credential = Credential(
            require_env("DINGTALK_CLIENT_ID"),
            require_env("DINGTALK_CLIENT_SECRET"),
        )
        temp_client = DingTalkStreamClient(credential)
        return temp_client.get_access_token()
    except RuntimeError as exc:
        logger.warning("获取 access_token 失败: %s", exc)
        return None


def _send_robot_private(
    staff_id: str,
    *,
    msg_key: str,
    msg_param: dict[str, str],
    client: Any | None = None,
    robot_code: str | None = None,
    log_label: str = "消息",
) -> None:
    uid = (staff_id or "").strip()
    if not uid:
        raise ValueError("staff_id 不能为空")
    if not msg_key.strip():
        raise ValueError("msg_key 不能为空")
    if not msg_param:
        raise ValueError("msg_param 不能为空")

    load_env_local()
    access_token = _get_access_token(client)
    if not access_token:
        raise RuntimeError("获取钉钉 access_token 失败")

    code = (robot_code or require_env("DINGTALK_CLIENT_ID")).strip()
    payload = {
        "robotCode": code,
        "userIds": [uid],
        "msgKey": msg_key.strip(),
        "msgParam": json.dumps(msg_param, ensure_ascii=False),
    }
    url = f"{DINGTALK_OPENAPI_ENDPOINT}/v1.0/robot/oToMessages/batchSend"
    headers = {
        "Content-Type": "application/json",
        "x-acs-dingtalk-access-token": access_token,
    }
    response = requests.post(url, headers=headers, json=payload, timeout=15)
    ok, detail = _response_succeeded(response)
    if not ok:
        raise RuntimeError(f"私聊发送失败：{detail}")
    try:
        data = response.json()
    except json.JSONDecodeError:
        data = {}
    if isinstance(data, dict):
        invalid = [str(x) for x in (data.get("invalidStaffIdList") or [])]
        if uid in invalid:
            raise RuntimeError(f"私聊发送失败：无效 userId {uid}")
        filtered = [str(x) for x in (data.get("filteredStaffIdList") or [])]
        if uid in filtered:
            raise RuntimeError(
                f"私聊发送失败：用户 {uid} 被过滤（可能未与机器人建立单聊）"
            )
    logger.info("私聊%s已发送 staff=%s… detail=%s", log_label, uid[:12], detail)


def send_robot_private_text(
    staff_id: str,
    text: str,
    *,
    client: Any | None = None,
    robot_code: str | None = None,
) -> None:
    """向指定用户私聊发送文本。"""
    body_text = (text or "").strip()
    if not body_text:
        raise ValueError("text 不能为空")
    _send_robot_private(
        staff_id,
        msg_key="sampleText",
        msg_param={"content": body_text},
        client=client,
        robot_code=robot_code,
        log_label="文本",
    )


def send_robot_private_markdown(
    staff_id: str,
    title: str,
    text: str,
    *,
    client: Any | None = None,
    robot_code: str | None = None,
) -> None:
    """向指定用户私聊发送 Markdown。"""
    body_text = (text or "").strip()
    title_text = (title or "").strip() or "Web Agent 结果"
    if not body_text:
        raise ValueError("text 不能为空")
    _send_robot_private(
        staff_id,
        msg_key="sampleMarkdown",
        msg_param={"title": title_text, "text": body_text},
        client=client,
        robot_code=robot_code,
        log_label="Markdown",
    )
