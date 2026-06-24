"""近义口令提示：快捷路由未命中时，避免误进 Agent。"""

from __future__ import annotations

from route_patterns import normalize_fuzzy_fast_command


def suggest_command_hint(text: str) -> str | None:
    """短句且像口令打错时，返回提示文案；否则 None。"""
    canonical = normalize_fuzzy_fast_command(text)
    if canonical is None:
        return None
    return (
        f"💡 你是不是想说：`{canonical}`？\n"
        "直接发送上述口令即可（更快，不走 Agent）。"
    )
