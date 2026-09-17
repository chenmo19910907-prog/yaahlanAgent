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


def format_at_user_prefix(
    at_label: str,
    *,
    at_user_id: str | None = None,
    avatar_ref: str | None = None,
) -> str:
    """@ 提及行：群 webhook 须写 staffId，客户端解析为蓝色姓名。"""
    mention = (at_user_id or "").strip() or (at_label or "").strip()
    if not mention:
        return ""
    ref = (avatar_ref or "").strip()
    if ref:
        if ref.startswith("<"):
            return f"{ref} @{mention}\n\n"
        if ref.startswith("data:"):
            return f"![]({ref}) @{mention}\n\n"
        if not ref.startswith(("http://", "https://", "@")):
            ref = f"@{ref}"
        return f"![]({ref}) @{mention}\n\n"
    return f"@{mention}\n\n"


def compose_quoted_markdown(
    body: str,
    quote_text: str | None,
    *,
    at_user_id: str | None = None,
    at_user_name: str | None = None,
    at_user_avatar_ref: str | None = None,
) -> str:
    quote = format_markdown_quote(quote_text) if quote_text else ""
    content = (body or "").strip()
    at_label = (at_user_name or "").strip() or (at_user_id or "").strip()
    prefix = format_at_user_prefix(
        at_label,
        at_user_id=at_user_id,
        avatar_ref=at_user_avatar_ref,
    )
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
    user_key: str | None = None,
    recall_label: str = "",
) -> str | None:
    """以 Markdown 发送回复，正文上方引用用户原提问。返回 processQueryKey（可撤回）。"""
    from dingtalk_robot_send import send_bot_markdown_reply
    from sent_message_store import get_sent_message_store

    markdown_title = title or markdown_title_from_quote(quote_text)
    process_key = send_bot_markdown_reply(
        handler,
        incoming,
        body,
        quote_text=quote_text,
        title=markdown_title,
    )
    uk = (user_key or "").strip()
    if process_key and uk:
        get_sent_message_store().register(
            uk,
            process_key,
            kind="markdown",
            label=recall_label or markdown_title,
        )
    return process_key
