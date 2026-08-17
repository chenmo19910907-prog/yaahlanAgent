"""Agent 回复后置检查：非管理员不应交付平台源文件。"""

from __future__ import annotations

from source_file_permission import (
    mentions_protected_source_delivery,
    source_file_denial_message,
)


def guard_readonly_source_file_reply(
    reply: str,
    *,
    allow_source_file: bool,
) -> str:
    if allow_source_file:
        return reply
    text = (reply or "").strip()
    if not text:
        return reply
    if mentions_protected_source_delivery(text):
        return source_file_denial_message()
    return reply
