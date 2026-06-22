"""钉钉群回复：Markdown 引用块展示用户原提问。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from export_delivery import DINGTALK_REPLY_MAX_CHARS, _truncate_inline

if TYPE_CHECKING:
    import dingtalk_stream

    from inbound_message import InboundMessage

MAX_QUOTE_CHARS = 180
DEFAULT_TITLE = "回复"
QUOTE_LABEL = "**提问**"


def _sanitize_quote_line(line: str) -> str:
    stripped = line.lstrip()
    if stripped.startswith(">"):
        return f"\\{line}"
    return line


def format_markdown_quote(text: str, *, max_chars: int = MAX_QUOTE_CHARS) -> str:
    body = (text or "").strip().replace("\r", "")
    if not body:
        return ""
    if len(body) > max_chars:
        body = body[: max_chars - 1] + "…"
    lines = [_sanitize_quote_line(line) for line in body.split("\n")]
    quoted = "\n".join(f"> {line}" if line else ">" for line in lines)
    return f"> {QUOTE_LABEL}\n{quoted}"


def markdown_title_from_quote(quote_text: str | None) -> str:
    if not quote_text:
        return DEFAULT_TITLE
    one_line = quote_text.strip().replace("\n", " ")
    if len(one_line) > 24:
        return one_line[:23] + "…"
    return one_line or DEFAULT_TITLE


def quote_text_from_inbound(inbound: InboundMessage | None) -> str | None:
    if inbound is None:
        return None
    text = (inbound.prompt_text() or inbound.text or "").strip()
    return text or None


def compose_quoted_markdown(
    body: str,
    quote_text: str | None,
    *,
    at_user_id: str | None = None,
) -> str:
    quote = format_markdown_quote(quote_text) if quote_text else ""
    content = (body or "").strip()
    prefix = f"@{at_user_id}\n\n" if at_user_id else ""
    if quote and content:
        return f"{prefix}{quote}\n\n---\n\n{content}"
    if quote:
        return f"{prefix}{quote}"
    if prefix and content:
        return f"{prefix}{content}"
    return content


def reply_quoted(
    handler: dingtalk_stream.ChatbotHandler,
    body: str,
    incoming: dingtalk_stream.ChatbotMessage,
    *,
    quote_text: str | None = None,
    title: str | None = None,
) -> None:
    """以 Markdown 发送回复，正文上方引用用户原提问。"""
    at_user_id = (incoming.sender_staff_id or "").strip() or None
    message = _truncate_inline(
        compose_quoted_markdown(body, quote_text, at_user_id=at_user_id),
        DINGTALK_REPLY_MAX_CHARS,
    )
    if not message.strip():
        return
    markdown_title = title or markdown_title_from_quote(quote_text)
    handler.reply_markdown(markdown_title, message, incoming)
