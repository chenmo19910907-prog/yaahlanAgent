"""识别「重新执行」指令。"""

from __future__ import annotations

import re

from inbound_message import strip_at_mentions

REPLAY_RE = re.compile(
    r"^(?:重新执行|重试|再来一次|再试一次|replay|retry)$",
    re.I,
)


def is_replay_command(text: str) -> bool:
    return bool(REPLAY_RE.match(strip_at_mentions(text or "").strip()))
