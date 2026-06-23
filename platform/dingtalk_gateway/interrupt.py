"""识别用户中断指令。"""

from __future__ import annotations

import re

from inbound_message import strip_at_mentions

INTERRUPT_RE = re.compile(
    r"^(?:中断操作|中断我的任务|中断|停止执行|停止|取消任务|取消|打断|stop|cancel)$",
    re.I,
)


def is_interrupt_command(text: str) -> bool:
    normalized = strip_at_mentions(text or "").strip()
    return bool(INTERRUPT_RE.match(normalized))
