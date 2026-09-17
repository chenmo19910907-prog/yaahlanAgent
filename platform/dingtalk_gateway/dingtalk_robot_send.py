"""企业机器人 OpenAPI 发送/撤回（可获 processQueryKey，sessionWebhook 不可撤回）。"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests
from dingtalk_stream import ChatbotHandler, ChatbotMessage
from dingtalk_stream.utils import DINGTALK_OPENAPI_ENDPOINT

from dingtalk_private_message import _get_access_token
from env_loader import load_env_local, require_env
from export_delivery import DINGTALK_REPLY_MAX_CHARS, _truncate_inline
from quoted_reply import compose_quoted_markdown, markdown_title_from_quote

logger = logging.getLogger("dingtalk-gateway")


def _sender_at_context(incoming: ChatbotMessage) -> tuple[str | None, str | None]:
    """@ 提及展示名与头像 URL（优先 sender_nick / profile 缓存）。"""
    nick = (incoming.sender_nick or "").strip()
    staff_id = (incoming.sender_staff_id or incoming.sender_id or "").strip()
    avatar_url = ""
    if staff_id:
        from dingtalk_user_profile import resolve_user_profile

        profile = resolve_user_profile(staff_id, known_name=nick, try_api=False)
        avatar_url = (profile.avatar_url or "").strip()
        if nick:
            return nick, avatar_url or None
        name = (profile.display_name or "").strip()
        if name and name != staff_id:
            return name, avatar_url or None
    if nick:
        return nick, avatar_url or None
    return None, avatar_url or None


def _sender_at_display_name(incoming: ChatbotMessage) -> str | None:
    name, _ = _sender_at_context(incoming)
    return name


def _compose_quoted_reply_markdown(
    handler: ChatbotHandler,
    incoming: ChatbotMessage,
    body: str,
    quote_text: str | None,
) -> str:
    at_user_id = (incoming.sender_staff_id or incoming.sender_id or "").strip() or None
    at_user_name, _ = _sender_at_context(incoming)
    return compose_quoted_markdown(
        body,
        quote_text,
        at_user_id=at_user_id,
        at_user_name=at_user_name,
    )


def parse_process_query_key(data: object) -> str | None:
    if not isinstance(data, dict):
        return None
    direct = data.get("processQueryKey")
    if direct:
        return str(direct).strip() or None
    result = data.get("result")
    if isinstance(result, dict):
        nested = result.get("processQueryKey")
        if nested:
            return str(nested).strip() or None
    if isinstance(result, list):
        for item in result:
            if not isinstance(item, dict):
                continue
            carrier = item.get("carrierId") or item.get("processQueryKey")
            if carrier:
                return str(carrier).strip() or None
    return None


def _robot_code(incoming: ChatbotMessage) -> str:
    code = (incoming.robot_code or "").strip()
    if code:
        return code
    load_env_local()
    return require_env("DINGTALK_CLIENT_ID").strip()


def _openapi_headers(access_token: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "x-acs-dingtalk-access-token": access_token,
    }


def _post_openapi(url: str, payload: dict[str, Any], *, access_token: str) -> dict[str, Any]:
    response = requests.post(
        url,
        headers=_openapi_headers(access_token),
        json=payload,
        timeout=20,
    )
    text = (response.text or "").strip()
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {text[:300]}")
    if not text:
        return {}
    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"返回不是合法 JSON: {text[:300]}") from exc
    if not isinstance(data, dict):
        return {}
    errcode = data.get("errcode")
    if errcode is not None and int(errcode) != 0:
        raise RuntimeError(f"errcode={errcode}, errmsg={data.get('errmsg')}")
    return data


def send_group_markdown_openapi(
    handler: ChatbotHandler,
    incoming: ChatbotMessage,
    *,
    title: str,
    text: str,
) -> str | None:
    conv_id = (incoming.conversation_id or "").strip()
    if not conv_id:
        raise RuntimeError("缺少 openConversationId，无法 OpenAPI 发群消息")
    access_token = _get_access_token(getattr(handler, "dingtalk_client", None))
    if not access_token:
        raise RuntimeError("获取钉钉 access_token 失败")
    payload = {
        "robotCode": _robot_code(incoming),
        "msgKey": "sampleMarkdown",
        "msgParam": json.dumps(
            {"title": (title or "回复").strip(), "text": text},
            ensure_ascii=False,
        ),
        "openConversationId": conv_id,
    }
    data = _post_openapi(
        f"{DINGTALK_OPENAPI_ENDPOINT}/v1.0/robot/groupMessages/send",
        payload,
        access_token=access_token,
    )
    key = parse_process_query_key(data)
    if key:
        logger.info("OpenAPI 群 Markdown 已发送 key=%s…", key[:16])
    return key


def send_oto_markdown_openapi(
    handler: ChatbotHandler,
    incoming: ChatbotMessage,
    *,
    title: str,
    text: str,
) -> str | None:
    staff_id = (incoming.sender_staff_id or incoming.sender_id or "").strip()
    if not staff_id:
        raise RuntimeError("缺少 sender_staff_id，无法 OpenAPI 发单聊消息")
    access_token = _get_access_token(getattr(handler, "dingtalk_client", None))
    if not access_token:
        raise RuntimeError("获取钉钉 access_token 失败")
    payload = {
        "robotCode": _robot_code(incoming),
        "userIds": [staff_id],
        "msgKey": "sampleMarkdown",
        "msgParam": json.dumps(
            {"title": (title or "回复").strip(), "text": text},
            ensure_ascii=False,
        ),
    }
    data = _post_openapi(
        f"{DINGTALK_OPENAPI_ENDPOINT}/v1.0/robot/oToMessages/batchSend",
        payload,
        access_token=access_token,
    )
    key = parse_process_query_key(data)
    if key:
        logger.info("OpenAPI 单聊 Markdown 已发送 staff=%s… key=%s…", staff_id[:12], key[:16])
    return key


def _at_user_ids_for_sender(incoming: ChatbotMessage) -> dict[str, str]:
    staff_id = (incoming.sender_staff_id or incoming.sender_id or "").strip()
    if not staff_id:
        return {}
    name, _ = _sender_at_context(incoming)
    display = (name or incoming.sender_nick or staff_id).strip()
    return {staff_id: display}


def send_markdown_card_deliver(
    handler: ChatbotHandler,
    incoming: ChatbotMessage,
    card_replier: Any,
    *,
    card_template_id: str,
    card_data: dict[str, Any],
    at_sender: bool = False,
) -> tuple[str, str | None]:
    """创建并投放 Markdown 互动卡片，返回 (card_instance_id, processQueryKey)。"""
    client = getattr(handler, "dingtalk_client", None) or card_replier.dingtalk_client
    access_token = client.get_access_token()
    if not access_token:
        raise RuntimeError("获取钉钉 access_token 失败")

    card_instance_id = card_replier.gen_card_id(incoming)
    create_body = {
        "cardTemplateId": card_template_id,
        "outTrackId": card_instance_id,
        "cardData": {"cardParamMap": card_data},
        "callbackType": "STREAM",
        "imGroupOpenSpaceModel": {"supportForward": True},
        "imRobotOpenSpaceModel": {"supportForward": True},
    }
    _post_openapi(
        f"{DINGTALK_OPENAPI_ENDPOINT}/v1.0/card/instances",
        create_body,
        access_token=access_token,
    )

    deliver_body: dict[str, Any] = {
        "outTrackId": card_instance_id,
        "userIdType": 1,
    }
    robot_code = _robot_code(incoming)
    if incoming.conversation_type == "2":
        deliver_body["openSpaceId"] = f"dtv1.card//IM_GROUP.{incoming.conversation_id}"
        deliver_body["imGroupOpenDeliverModel"] = {"robotCode": robot_code}
        if at_sender:
            at_map = _at_user_ids_for_sender(incoming)
            if at_map:
                deliver_body["imGroupOpenDeliverModel"]["atUserIds"] = at_map
    elif incoming.conversation_type == "1":
        deliver_body["openSpaceId"] = f"dtv1.card//IM_ROBOT.{incoming.sender_staff_id}"
        deliver_body["imRobotOpenDeliverModel"] = {
            "spaceType": "IM_ROBOT",
            "robotCode": robot_code,
        }
    else:
        deliver_body["openSpaceId"] = f"dtv1.card//IM_GROUP.{incoming.conversation_id or ''}"
        deliver_body["imGroupOpenDeliverModel"] = {"robotCode": robot_code}

    deliver_data = _post_openapi(
        f"{DINGTALK_OPENAPI_ENDPOINT}/v1.0/card/instances/deliver",
        deliver_body,
        access_token=access_token,
    )
    process_key = parse_process_query_key(deliver_data)
    return card_instance_id, process_key


def send_bot_markdown_reply(
    handler: ChatbotHandler,
    incoming: ChatbotMessage,
    body: str,
    *,
    quote_text: str | None = None,
    title: str | None = None,
    use_openapi: bool = True,
) -> str | None:
    """发送 Markdown 回复；群聊走 sessionWebhook 以正确 @ 高亮，单聊可走 OpenAPI。"""
    message = _truncate_inline(
        _compose_quoted_reply_markdown(handler, incoming, body, quote_text),
        DINGTALK_REPLY_MAX_CHARS,
    )
    if not message.strip():
        return None
    markdown_title = title or markdown_title_from_quote(quote_text)

    # 群聊：OpenAPI/互动卡片无法像 webhook 一样渲染 @，与旧版一致走 reply_markdown
    if (incoming.conversation_type or "").strip() == "2":
        handler.reply_markdown(markdown_title, message, incoming)
        return None

    if use_openapi:
        try:
            if incoming.conversation_type == "1":
                return send_oto_markdown_openapi(
                    handler,
                    incoming,
                    title=markdown_title,
                    text=message,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAPI 发 Markdown 失败，回退 sessionWebhook: %s", exc)

    handler.reply_markdown(markdown_title, message, incoming)
    return None


def send_final_result_card(
    handler: ChatbotHandler,
    incoming: ChatbotMessage,
    *,
    title: str,
    body: str,
    quote_text: str | None = None,
    user_key: str = "",
) -> bool:
    """投放最终结果 Markdown 互动卡片（含提问引用）。"""
    import dingtalk_stream

    at_user_id = (incoming.sender_staff_id or "").strip() or None
    message = _truncate_inline(
        _compose_quoted_reply_markdown(handler, incoming, body, quote_text),
        DINGTALK_REPLY_MAX_CHARS,
    )
    if not message.strip():
        return False
    card_title = (title or "回复").strip()
    md_card = dingtalk_stream.MarkdownCardInstance(handler.dingtalk_client, incoming)
    md_card.set_title_and_logo(card_title, "")
    card_data = md_card._get_card_data(message)
    try:
        _, process_key = send_markdown_card_deliver(
            handler,
            incoming,
            md_card,
            card_template_id=md_card.card_template_id,
            card_data=card_data,
            at_sender=bool(at_user_id),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("最终结果卡片投放失败: %s", exc)
        return False
    uk = (user_key or "").strip()
    if process_key and uk:
        from sent_message_store import get_sent_message_store

        get_sent_message_store().register(
            uk,
            process_key,
            kind="result_card",
            label=card_title,
        )
    if process_key:
        logger.info("最终结果卡片已投放 key=%s… len=%d", process_key[:16], len(message))
        return True
    logger.warning("最终结果卡片投放成功但未返回 processQueryKey")
    return False


def recall_robot_messages(
    handler: ChatbotHandler,
    incoming: ChatbotMessage,
    process_query_keys: list[str],
) -> tuple[int, str | None]:
    keys = [str(k).strip() for k in process_query_keys if str(k).strip()]
    if not keys:
        return 0, "没有可撤回的消息记录"
    access_token = _get_access_token(getattr(handler, "dingtalk_client", None))
    if not access_token:
        return 0, "获取钉钉 access_token 失败"

    robot_code = _robot_code(incoming)
    recalled = 0
    last_error: str | None = None
    for offset in range(0, len(keys), 20):
        batch = keys[offset : offset + 20]
        try:
            if incoming.conversation_type == "2":
                conv_id = (incoming.conversation_id or "").strip()
                if not conv_id:
                    return recalled, "缺少 openConversationId"
                _post_openapi(
                    f"{DINGTALK_OPENAPI_ENDPOINT}/v1.0/robot/groupMessages/recall",
                    {
                        "openConversationId": conv_id,
                        "robotCode": robot_code,
                        "processQueryKeys": batch,
                    },
                    access_token=access_token,
                )
            else:
                _post_openapi(
                    f"{DINGTALK_OPENAPI_ENDPOINT}/v1.0/robot/otoMessages/batchRecall",
                    {
                        "robotCode": robot_code,
                        "processQueryKeys": batch,
                    },
                    access_token=access_token,
                )
            recalled += len(batch)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            logger.warning("撤回消息失败 batch=%s: %s", len(batch), exc)
            break
    return recalled, last_error
