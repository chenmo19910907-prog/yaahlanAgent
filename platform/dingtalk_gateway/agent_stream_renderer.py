"""将 Cursor SDK 流式事件渲染为钉钉 AI 卡片 Markdown。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

THINKING_MAX_CHARS = 600
WEB_THINKING_MAX_CHARS = 2400
WEB_ANSWER_PREVIEW_CHARS = 1200
WEB_TOOL_LINES_MAX = 20
TOOL_LINES_MAX = 12

_PROMPT_ECHO_LINE_RES = (
    re.compile(r"^用户$"),
    re.compile(r"^用户消息"),
    re.compile(r"^---+$"),
    re.compile(r"^<!--"),
    re.compile(r"^会话上下文"),
)


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


def _sanitize_thinking_line(line: str) -> str:
    s = (line or "").strip()
    while s.startswith(">"):
        s = s[1:].lstrip()
    return s


def _is_prompt_echo_line(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return False
    return any(p.match(s) for p in _PROMPT_ECHO_LINE_RES)


def sanitize_web_thinking(text: str) -> str:
    """Web 思考区：去掉 prompt 回显行（如单独一行的「用户」「用户消息…」）。"""
    if not text:
        return ""
    lines: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if _is_prompt_echo_line(stripped):
            continue
        lines.append(_sanitize_thinking_line(raw))
    return "\n".join(lines).strip()


def _format_thinking_blockquote(text: str, max_chars: int) -> str:
    """钉钉卡片等：blockquote 展示思考片段（保留尾部最新内容）。"""
    body = _tail(text.strip(), max_chars)
    lines = body.splitlines() or [body]
    quoted = "\n".join(f"> {_sanitize_thinking_line(line)}" if line else ">" for line in lines)
    return f"🤔 **思考中**\n\n{quoted}"


def _format_thinking_for_web(text: str, max_chars: int) -> str:
    """Web 流式：用 ### 标题 + 段落，由前端 stream-thinking 完整展示（不经 marked）。"""
    body = _tail(text.strip(), max_chars)
    raw_lines = body.splitlines() or [body]
    lines = [_sanitize_thinking_line(ln) for ln in raw_lines]
    lines = [ln for ln in lines if ln]
    if not lines:
        return ""
    return f"### 思考中\n\n" + "\n".join(lines)


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


def append_process_summary(answer: str, process_md: str) -> str:
    """在 assistant 正文后追加思考/工具摘要（详细模式）。"""
    body = (answer or "").rstrip()
    appendix = (process_md or "").strip()
    if not appendix:
        return body
    if not body:
        return appendix
    return f"{body}\n\n---\n\n{appendix}"


class AgentStreamRenderer:
    """累积 thinking / answer / tool 行，生成可刷新的 Markdown 快照。"""

    def __init__(self, *, show_thinking: bool = True) -> None:
        self._show_thinking = show_thinking
        self._thinking = ""
        self._pre_tool_thinking = ""
        self._answer = ""
        self._tool_lines: list[str] = []
        self._status_hint = ""

    def apply(self, update: Any) -> bool:
        utype = _update_type(update)
        if utype == "thinking-delta" and self._show_thinking:
            return self.update_thinking(_update_text(update))
        if utype == "text-delta":
            self._answer += _update_text(update)
            return True
        if utype == "tool-call-started":
            self._capture_pre_tool_thinking()
            self._tool_lines.append(f"> 🔧 {_tool_name(update)} …")
            if len(self._tool_lines) > TOOL_LINES_MAX:
                self._tool_lines = self._tool_lines[-TOOL_LINES_MAX:]
            return True
        if utype == "tool-call-completed":
            self._capture_pre_tool_thinking()
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

    def update_thinking(self, text: str) -> bool:
        """兼容 thinking 增量与全量快照（逻辑同 update_answer）。"""
        if not text or not self._show_thinking:
            return False
        current = self._thinking
        if text == current:
            return False
        if not current:
            self._thinking = text
            return True
        if text.startswith(current):
            self._thinking = text
            return True
        if current.startswith(text):
            return False
        self._thinking = f"{current}{text}"
        return True

    def append_thinking(self, chunk: str) -> bool:
        return self.update_thinking(chunk)

    def _capture_pre_tool_thinking(self) -> None:
        """工具开始前冻结 assistant 流式正文，供执行中持续展示。"""
        if self._pre_tool_thinking.strip():
            return
        if self._thinking.strip():
            self._pre_tool_thinking = self._thinking.strip()
        elif self._answer.strip():
            self._pre_tool_thinking = self._answer.strip()

    def append_tool_step(self, name: str, *, completed: bool = False) -> bool:
        self._capture_pre_tool_thinking()
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

    def _web_display_thinking(self) -> str:
        """Web 执行中思考区：SDK thinking + 工具调用前正文合并展示，互不覆盖。"""
        if not self._show_thinking:
            return ""
        pre = sanitize_web_thinking(self._pre_tool_thinking.strip())
        sdk = sanitize_web_thinking(self._thinking.strip())
        if sdk and pre:
            if sdk.startswith(pre) or pre in sdk:
                return sdk
            if pre.startswith(sdk):
                return pre
            return f"{pre}\n\n{sdk}"
        if sdk:
            return sdk
        if pre:
            return pre
        if self._answer.strip() and not self._tool_lines:
            return sanitize_web_thinking(self._answer.strip())
        return ""

    def markdown(self) -> str:
        parts: list[str] = []
        if self._show_thinking and self._thinking.strip():
            parts.append(_format_thinking_blockquote(self._thinking, THINKING_MAX_CHARS))
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

    def web_process_payload(self) -> dict[str, Any]:
        """Web 执行中过程区：思考全文 + 工具链（不含回复预览，避免与完成态 Markdown 重复）。"""
        thinking = ""
        raw = self._web_display_thinking()
        if raw:
            thinking = _tail(raw, WEB_THINKING_MAX_CHARS)
        tools: list[str] = []
        for ln in self._tool_lines[-WEB_TOOL_LINES_MAX:]:
            text = _strip_tool_decoration(ln).lstrip("·").strip()
            if text:
                tools.append(text)
        return {"thinking": thinking, "tools": tools}

    def markdown_for_web(self) -> str:
        """Web Agent 执行中白框：思考全文 + 工具链（不含回复预览，完成后再 renderMarkdown）。"""
        parts: list[str] = []
        raw_thinking = self._web_display_thinking()
        if raw_thinking:
            parts.append(_format_thinking_for_web(raw_thinking, WEB_THINKING_MAX_CHARS))
        if self._tool_lines:
            tools = [_strip_tool_decoration(ln) for ln in self._tool_lines[-WEB_TOOL_LINES_MAX:]]
            tools = [t for t in tools if t]
            if tools:
                if parts:
                    parts.append("")
                parts.append("### 执行工作\n\n" + "\n".join(tools))
        elif self._status_hint and not parts:
            parts.append(self._status_hint)
        if not parts:
            return "⏳ Agent 启动中…"
        return "\n".join(parts)

    def process_summary_markdown(self) -> str:
        """详细模式最终结果附录：思考过程 + 执行工作（完整内容，非流式截断）。"""
        parts: list[str] = []
        if self._thinking.strip():
            parts.append("### 思考过程\n\n" + self._thinking.strip())
        if self._tool_lines:
            tools = [_strip_tool_decoration(ln) for ln in self._tool_lines]
            tools = [line for line in tools if line]
            if tools:
                parts.append("### 执行工作\n\n" + "\n".join(tools))
        return "\n\n".join(parts)

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
