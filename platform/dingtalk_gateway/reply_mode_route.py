"""钉钉回复详略切换口令（精简 / 标准 / 详细），全员统一。"""

from __future__ import annotations

from reply_mode_store import MODE_LABELS, get_reply_mode_store
from route_patterns import parse_reply_mode_request

_SET_ACK = {
    "concise": "已切换为**精简回复**（全员统一）。后续只给结论与必要数字/链接，省略背景与耗时尾注。",
    "standard": "已切换为**标准回复**（全员统一，默认）。",
    "detailed": "已切换为**详细回复**（全员统一）。将补充步骤、依据与边界说明。",
}


def handle_reply_mode_message(text: str) -> str | None:
    """解析回复详略口令；命中则写入全员设置并返回确认文案，否则 None。"""
    parsed = parse_reply_mode_request(text)
    if parsed is None:
        return None
    store = get_reply_mode_store()
    if parsed == "query":
        mode = store.get()
        label = MODE_LABELS.get(mode, mode)
        return (
            f"当前机器人回复详略（**全员统一**）：**{label}**。\n"
            "发送「精简回复」「标准回复」或「详细回复」可切换（对所有用户生效）。"
        )
    store.set(parsed)
    return _SET_ACK.get(parsed, _SET_ACK["standard"])
