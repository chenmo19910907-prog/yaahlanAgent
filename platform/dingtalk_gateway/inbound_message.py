"""解析钉钉入站消息：纯文本、图片、富文本（图文链接）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from dingtalk_stream import ChatbotMessage

AT_BOT_PATTERN = re.compile(r"@[^\s@]+\s*")
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

SUPPORTED_MESSAGE_TYPES = frozenset({"text", "picture", "richText", "file", "audio"})
UNSUPPORTED_TYPE_HINT = (
    "暂不支持该消息类型，请改用文字、图片或 alidocs 链接。"
    "若需传文件，可先上传到钉钉文档后把链接发给机器人。"
)
PICTURE_ONLY_DEFAULT = "请根据附图理解并完成任务。"


def strip_at_mentions(text: str) -> str:
    return AT_BOT_PATTERN.sub("", text or "").strip()


@dataclass
class InboundMessage:
    text: str = ""
    image_download_codes: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip() and not self.image_download_codes and not self.links

    def prompt_text(self) -> str:
        parts: list[str] = []
        if self.text.strip():
            parts.append(self.text.strip())
        elif self.image_download_codes:
            parts.append(PICTURE_ONLY_DEFAULT)
        if self.links:
            parts.append("链接：\n" + "\n".join(self.links))
        return "\n\n".join(parts)

    def summary_label(self) -> str:
        parts: list[str] = []
        if self.text.strip():
            parts.append("文字")
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


def parse_inbound_message(incoming: ChatbotMessage) -> InboundMessage:
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

    return InboundMessage(
        text=combined_text,
        image_download_codes=codes,
        links=_dedupe_links(links),
    )
