"""识别撤回指令并调用 OpenAPI 撤回机器人消息。"""

from __future__ import annotations

import re
from typing import Any

import dingtalk_stream

from dingtalk_robot_send import recall_robot_messages
from inbound_message import strip_at_mentions
from sent_message_store import get_sent_message_store

RECALL_LAST_RE = re.compile(
    r"^(?:撤回上一条|撤回消息|撤回机器人消息|撤回)$",
    re.I,
)
RECALL_BURST_RE = re.compile(
    r"^(?:撤回本次回复|撤回本次|撤回刚才的回复|撤回刚才)$",
    re.I,
)


def is_recall_command(text: str) -> bool:
    normalized = strip_at_mentions(text or "").strip()
    return bool(RECALL_LAST_RE.match(normalized) or RECALL_BURST_RE.match(normalized))


def is_recall_burst_command(text: str) -> bool:
    normalized = strip_at_mentions(text or "").strip()
    return bool(RECALL_BURST_RE.match(normalized))


def handle_recall_command(
    handler: Any,
    incoming: dingtalk_stream.ChatbotMessage,
    *,
    user_key: str,
    text: str,
) -> str:
    store = get_sent_message_store()
    if is_recall_burst_command(text):
        keys = store.pop_burst_keys(user_key)
        mode = "本次回复"
    else:
        keys = store.pop_recent_keys(user_key, count=1)
        mode = "上一条"

    if not keys:
        return "暂无可撤回的消息（仅支持撤回 24 小时内、经 OpenAPI 发送的机器人消息）。"

    recalled, err = recall_robot_messages(handler, incoming, keys)
    if recalled <= 0:
        detail = err or "未知错误"
        if "expired" in detail.lower():
            return "消息已超过 24 小时，无法撤回。"
        return f"撤回失败：{detail}"

    if err:
        return f"已撤回 {recalled}/{len(keys)} 条{mode}消息；部分失败：{err}"
    if recalled == 1:
        return f"✅ 已撤回{mode}消息。"
    return f"✅ 已撤回 {recalled} 条{mode}消息。"
