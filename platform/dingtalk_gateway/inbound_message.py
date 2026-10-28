"""解析钉钉入站消息：纯文本、图片、富文本（图文链接）、引用回复。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from dingtalk_stream import ChatbotMessage

AT_BOT_PATTERN = re.compile(r"@[^\s@]+\s*")
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

SUPPORTED_MESSAGE_TYPES = frozenset({"text", "picture", "richText", "file", "audio"})
UNSUPPORTED_TYPE_HINT = (
    "暂不支持该消息类型，请改用文字、图片或 alidocs 链接。"
    "若需传文件，可先上传到钉钉文档后把链接发给机器人。"
)
PICTURE_ONLY_DEFAULT = "请根据附图理解并完成任务。"
REPLIED_TEXT_MAX_CHARS = 4000
REPLIED_QUOTE_LABEL = "【引用消息】"


def strip_at_mentions(text: str) -> str:
    return AT_BOT_PATTERN.sub("", text or "").strip()


@dataclass
class InboundMessage:
    text: str = ""
    replied_text: str = ""
    image_download_codes: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return (
            not self.text.strip()
            and not self.replied_text.strip()
            and not self.image_download_codes
            and not self.links
        )

    def prompt_text(self) -> str:
        parts: list[str] = []
        if self.text.strip():
            parts.append(self.text.strip())
        elif self.image_download_codes:
            parts.append(PICTURE_ONLY_DEFAULT)
        if self.replied_text.strip():
            parts.append(f"{REPLIED_QUOTE_LABEL}\n{self.replied_text.strip()}")
        if self.links:
            parts.append("链接：\n" + "\n".join(self.links))
        return "\n\n".join(parts)

    def summary_label(self) -> str:
        parts: list[str] = []
        if self.text.strip():
            parts.append("文字")
        if self.replied_text.strip():
            parts.append("引用")
        if self.image_download_codes:
            parts.append(f"{len(self.image_download_codes)}图")
        if self.links:
            parts.append(f"{len(self.links)}链接")
        return "+".join(parts) if parts else "消息"


def _dedupe_links(links: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for raw in links:
        link = raw.strip().rstrip(".,;:)")
        if not link or link in seen:
            continue
        seen.add(link)
        unique.append(link)
    return unique


def _extract_links_from_rich_item(item: dict) -> list[str]:
    found: list[str] = []
    for key in ("href", "link", "url"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            found.append(value.strip())
    item_type = str(item.get("type", "")).lower()
    if item_type in {"link", "url"}:
        for key in ("href", "url", "link"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                found.append(value.strip())
    return found


def _parse_json_object(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _truncate_replied(text: str) -> str:
    body = (text or "").strip()
    if len(body) <= REPLIED_TEXT_MAX_CHARS:
        return body
    return body[: REPLIED_TEXT_MAX_CHARS - 1].rstrip() + "…"


def _rich_text_body(content_obj: dict[str, Any]) -> str:
    rich_list = content_obj.get("richText")
    if not isinstance(rich_list, list):
        return ""
    parts: list[str] = []
    for item in rich_list:
        if not isinstance(item, dict):
            continue
        text_value = item.get("text")
        if isinstance(text_value, str) and text_value.strip():
            parts.append(text_value.strip())
    return "".join(parts).strip()


def _body_from_replied_msg(replied_msg: dict[str, Any], *, max_depth: int) -> str:
    if max_depth <= 0:
        return ""
    msg_type = str(replied_msg.get("msgType") or "text").lower()
    content_obj = _parse_json_object(replied_msg.get("content"))

    if msg_type == "text":
        chunks: list[str] = []
        if content_obj:
            main = (content_obj.get("text") or "").strip()
            if main:
                chunks.append(main)
            if content_obj.get("isReplyMsg"):
                nested = _extract_replied_text_from_container(content_obj, max_depth=max_depth - 1)
                if nested:
                    chunks.append(nested)
        fallback = (replied_msg.get("text") or "").strip()
        if fallback and not chunks:
            chunks.append(fallback)
        return "\n".join(chunks).strip()

    if msg_type == "richtext":
        if content_obj:
            body = _rich_text_body(content_obj)
            if body:
                return body
        return "[富文本]"

    placeholders = {
        "picture": "[图片]",
        "video": "[视频]",
        "audio": "[语音]",
        "file": "[文件]",
        "markdown": "[Markdown]",
        "interactivecard": "[互动卡片]",
    }
    if msg_type in placeholders:
        if msg_type == "file" and content_obj:
            name = (content_obj.get("fileName") or "").strip()
            return f"[文件: {name}]" if name else placeholders[msg_type]
        if msg_type == "audio" and content_obj:
            rec = (content_obj.get("recognition") or "").strip()
            return rec or placeholders[msg_type]
        if msg_type == "markdown" and content_obj:
            md = (content_obj.get("text") or "").strip()
            return md or placeholders[msg_type]
        return placeholders[msg_type]

    return f"[{msg_type}消息]"


def _extract_replied_text_from_container(
    container: dict[str, Any] | None,
    *,
    max_depth: int = 3,
) -> str:
    if not container or max_depth <= 0:
        return ""

    quote = container.get("quoteMessage")
    if isinstance(quote, dict):
        quote_text = quote.get("text")
        if isinstance(quote_text, dict):
            legacy = (quote_text.get("content") or "").strip()
            if legacy:
                return legacy
        if isinstance(quote_text, str) and quote_text.strip():
            return quote_text.strip()

    if not container.get("isReplyMsg"):
        return ""

    replied = container.get("repliedMsg")
    if not isinstance(replied, dict):
        return ""
    return _body_from_replied_msg(replied, max_depth=max_depth)


def _text_container_from_incoming(
    incoming: ChatbotMessage,
    raw: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if raw and isinstance(raw.get("text"), dict):
        return raw["text"]
    if incoming.message_type == "text" and incoming.text:
        return incoming.text.to_dict()
    return None


def apply_replied_fallback(
    inbound: InboundMessage,
    incoming: ChatbotMessage,
    store: Any,
    *,
    conversation_id: str | None = None,
    sender_id: str | None = None,
    sender_staff_id: str | None = None,
    sender_nick: str | None = None,
    conversation_type: str | None = None,
) -> None:
    """引用机器人卡片等仅有 msgId 时，用同会话最近一次完整回复兜底。"""
    if inbound.replied_text.strip():
        return
    container = _text_container_from_incoming(incoming, None)
    if not container or not container.get("isReplyMsg"):
        return
    fallback = store.get_last_full_reply(
        conversation_id,
        sender_id=sender_id,
        sender_staff_id=sender_staff_id,
        sender_nick=sender_nick,
        conversation_type=conversation_type,
    )
    if fallback and fallback.strip():
        inbound.replied_text = _truncate_replied(fallback)


def parse_inbound_message(
    incoming: ChatbotMessage,
    raw: dict[str, Any] | None = None,
) -> InboundMessage:
    message_type = incoming.message_type or "text"
    if message_type not in SUPPORTED_MESSAGE_TYPES:
        if message_type in {"file", "audio"}:
            return InboundMessage(text=UNSUPPORTED_TYPE_HINT)
        return InboundMessage()

    texts: list[str] = []
    codes: list[str] = []
    links: list[str] = []

    if message_type == "text" and incoming.text:
        texts.append(incoming.text.content or "")
    elif message_type == "picture" and incoming.image_content and incoming.image_content.download_code:
        codes.append(incoming.image_content.download_code)
    elif message_type == "richText" and incoming.rich_text_content:
        for item in incoming.rich_text_content.rich_text_list or []:
            if not isinstance(item, dict):
                continue
            text_value = item.get("text")
            if isinstance(text_value, str) and text_value:
                texts.append(text_value)
            code = item.get("downloadCode") or item.get("pictureDownloadCode")
            if isinstance(code, str) and code:
                codes.append(code)
            links.extend(_extract_links_from_rich_item(item))

    combined_text = strip_at_mentions("\n".join(texts))
    links.extend(URL_PATTERN.findall(combined_text))

    replied_raw = _extract_replied_text_from_container(
        _text_container_from_incoming(incoming, raw),
    )
    replied_text = _truncate_replied(strip_at_mentions(replied_raw))
    links.extend(URL_PATTERN.findall(replied_text))

    return InboundMessage(
        text=combined_text,
        replied_text=replied_text,
        image_download_codes=codes,
        links=_dedupe_links(links),
    )
