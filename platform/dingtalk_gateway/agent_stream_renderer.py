"""将 Cursor SDK 流式事件渲染为钉钉 AI 卡片 Markdown。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

THINKING_MAX_CHARS = 600
TOOL_LINES_MAX = 12


def _update_type(update: Any) -> str:
    if isinstance(update, Mapping):
        return str(update.get("type") or "")
    return str(getattr(update, "type", "") or "")


def _update_text(update: Any) -> str:
    if isinstance(update, Mapping):
        return str(update.get("text") or "")
    return str(getattr(update, "text", "") or "")


def _tool_name(update: Any) -> str:
    tool_call: Any = None
    if isinstance(update, Mapping):
        tool_call = update.get("toolCall") or update.get("tool_call")
    else:
        tool_call = getattr(update, "tool_call", None)
    if isinstance(tool_call, Mapping):
        for key in ("name", "toolName", "tool"):
            value = tool_call.get(key)
            if value:
                return str(value)
    return "工具"


def _tail(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return "…" + text[-max_chars:]


def _strip_tool_decoration(line: str) -> str:
    """卡片专用：去掉工具行的引用符与 emoji，保留纯文本。"""
    text = (line or "").lstrip("> ").strip()
    for token in ("🔧 ", "✅ ", "🔧", "✅"):
        text = text.replace(token, "")
    text = text.strip()
    if text.endswith(" …"):
        text = text[:-2] + "…"
    return f"· {text}" if text else ""


def assistant_text_chunk(sdk_message: Any) -> str:
    """从 sdk_message(assistant) 提取本次增量文本。"""
    if getattr(sdk_message, "type", "") != "assistant":
        return ""
    content = getattr(getattr(sdk_message, "message", None), "content", ())
    parts: list[str] = []
    for block in content or ():
        text = getattr(block, "text", "")
        if text:
            parts.append(text)
    return "".join(parts)


def tool_name_from_step(step: Any) -> str:
    step_type = getattr(step, "type", "")
    if step_type == "thinkingMessage":
        return ""
    if step_type != "toolCall":
        return ""
    message = getattr(step, "message", None)
    if isinstance(message, Mapping):
        for key in ("name", "toolName", "tool", "type"):
            value = message.get(key)
            if value and str(value).strip():
                return str(value).strip()
    return "工具"


def thinking_text_from_step(step: Any) -> str:
    if getattr(step, "type", "") != "thinkingMessage":
        return ""
    message = getattr(step, "message", None)
    if message is None:
        return ""
    text = getattr(message, "text", "")
    if text:
        return str(text)
    if isinstance(message, Mapping):
        return str(message.get("text") or "")
    return ""


class AgentStreamRenderer:
    """累积 thinking / answer / tool 行，生成可刷新的 Markdown 快照。"""

    def __init__(self, *, show_thinking: bool = True) -> None:
        self._show_thinking = show_thinking
        self._thinking = ""
        self._answer = ""
        self._tool_lines: list[str] = []
        self._status_hint = ""

    def apply(self, update: Any) -> bool:
        utype = _update_type(update)
        if utype == "thinking-delta" and self._show_thinking:
            self._thinking += _update_text(update)
            return True
        if utype == "text-delta":
            self._answer += _update_text(update)
            return True
        if utype == "tool-call-started":
            self._tool_lines.append(f"> 🔧 {_tool_name(update)} …")
            if len(self._tool_lines) > TOOL_LINES_MAX:
                self._tool_lines = self._tool_lines[-TOOL_LINES_MAX:]
            return True
        if utype == "tool-call-completed":
            self._tool_lines.append(f"> ✅ {_tool_name(update)}")
            if len(self._tool_lines) > TOOL_LINES_MAX:
                self._tool_lines = self._tool_lines[-TOOL_LINES_MAX:]
            return True
        return False

    def append_answer(self, chunk: str) -> bool:
        if not chunk:
            return False
        self._answer += chunk
        return True

    def update_answer(self, text: str) -> bool:
        """兼容全量快照与增量：SDK assistant message 多为当前完整文本快照。

        - 新文本以当前 answer 为前缀（或反之）→ 视为全量快照，替换。
        - 否则视为新增片段，追加。
        """
        if not text:
            return False
        current = self._answer
        if text == current:
            return False
        if not current:
            self._answer = text
            return True
        if text.startswith(current):
            # 全量快照增长
            self._answer = text
            return True
        if current.startswith(text):
            # 旧快照更长（乱序），保留较长者
            return False
        # 与现有内容不重叠 → 追加新片段
        self._answer = f"{current}{text}"
        return True

    def append_thinking(self, chunk: str) -> bool:
        if not chunk or not self._show_thinking:
            return False
        self._thinking += chunk
        return True

    def append_tool_step(self, name: str, *, completed: bool = False) -> bool:
        label = name or "工具"
        line = f"> ✅ {label}" if completed else f"> 🔧 {label} …"
        self._tool_lines.append(line)
        if len(self._tool_lines) > TOOL_LINES_MAX:
            self._tool_lines = self._tool_lines[-TOOL_LINES_MAX:]
        return True

    def set_status_hint(self, hint: str) -> bool:
        hint = hint.strip()
        if not hint or hint == self._status_hint:
            return False
        self._status_hint = hint
        return True

    def markdown(self) -> str:
        parts: list[str] = []
        if self._show_thinking and self._thinking.strip():
            parts.append("🤔 **思考中**\n\n> " + _tail(self._thinking.strip(), THINKING_MAX_CHARS))
        if self._answer.strip():
            if parts:
                parts.append("")
            parts.append(self._answer.strip())
        if self._tool_lines:
            if parts:
                parts.append("")
            parts.extend(self._tool_lines)
        if self._status_hint and not self._answer.strip():
            if parts:
                parts.append("")
            parts.append(self._status_hint)
        if not parts:
            return "⏳ Agent 启动中…"
        return "\n".join(parts)

    def markdown_for_card(self) -> str:
        """钉钉卡片专用：单行紧凑，避免思考块撑高导致抖动。"""
        from progress_message import STREAMING_CARD_LINE_BREAK

        parts: list[str] = []
        if self._tool_lines:
            parts.extend(_strip_tool_decoration(ln) for ln in self._tool_lines[-4:])
        elif self._show_thinking and self._thinking.strip():
            parts.append("思考中…")
        if self._answer.strip():
            text = self._answer.strip()
            if len(text) > 280:
                text = "…" + text[-280:]
            parts.append(text)
        if not parts:
            return ""
        joined = STREAMING_CARD_LINE_BREAK.join(parts)
        return joined.replace("\n\n", STREAMING_CARD_LINE_BREAK).replace("\n", STREAMING_CARD_LINE_BREAK)
