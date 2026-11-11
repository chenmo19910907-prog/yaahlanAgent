# -*- coding: utf-8 -*-
"""从 Cursor SDK 流式事件中提取 Shell 终端输出（不经大模型上下文）。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from agent_stream_renderer import _update_type
from run_child_processes import _extract_shell_command

_SHELL_TOOL_NAMES = frozenset(
    {"shell", "run_terminal_cmd", "bash", "terminal", "execute_command"}
)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_from_mapping(data: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        raw = data.get(key)
        if raw is None:
            continue
        if isinstance(raw, str):
            text = raw
        elif isinstance(raw, (bytes, bytearray)):
            text = raw.decode("utf-8", errors="replace")
        else:
            text = str(raw)
        if text:
            return text
    return ""


def _chunks_from_shell_event(event: Mapping[str, Any]) -> list[str]:
    if not event:
        return []
    for key in ("data", "stdout", "stderr", "text", "chunk", "content", "output", "delta"):
        text = _string_from_mapping(event, key)
        if text:
            return [text]
    nested = event.get("shellOutput") or event.get("shell_output")
    if isinstance(nested, Mapping):
        parts: list[str] = []
        for key in ("stdout", "stderr"):
            piece = _string_from_mapping(nested, key)
            if piece:
                parts.append(piece)
        if parts:
            return parts
    return []


def _command_from_args(args: Any) -> str:
    if isinstance(args, str) and args.strip():
        text = args.strip()
        if text.startswith("{"):
            try:
                args = json.loads(text)
            except json.JSONDecodeError:
                return text
        else:
            return text
    if isinstance(args, Mapping):
        for key in ("command", "cmd", "script", "input"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _stdout_from_mapping_blob(blob: Mapping[str, Any]) -> str:
    parts: list[str] = []
    success = blob.get("success")
    if isinstance(success, Mapping):
        for key in ("stdout", "stderr"):
            piece = _string_from_mapping(success, key)
            if piece:
                parts.append(piece)
        if parts:
            return "".join(parts)
    shell_out = blob.get("shellOutput") or blob.get("shell_output")
    if isinstance(shell_out, Mapping):
        for key in ("stdout", "stderr"):
            piece = _string_from_mapping(shell_out, key)
            if piece:
                parts.append(piece)
        if parts:
            return "".join(parts)
    for sub in (
        "stdout",
        "stderr",
        "text",
        "output",
        "content",
        "value",
        "rejected",
    ):
        text = _string_from_mapping(blob, sub)
        if text:
            return text
    return ""


def _stdout_from_tool_result(tool_call: Mapping[str, Any]) -> str:
    for key in ("result", "output", "stdout", "content"):
        raw = tool_call.get(key)
        if raw is None:
            continue
        if isinstance(raw, str):
            return raw
        if isinstance(raw, Mapping):
            text = _stdout_from_mapping_blob(raw)
            if text:
                return text
            try:
                return json.dumps(raw, ensure_ascii=False)
            except (TypeError, ValueError):
                return str(raw)
        return str(raw)
    return ""


def _is_shell_tool(name: str, args: Any) -> bool:
    key = (name or "").strip().lower()
    if key in _SHELL_TOOL_NAMES:
        return True
    return bool(_command_from_args(args))


def consume_shell_stream_chunks(update: Any) -> list[str]:
    """返回本次 update 应对终端展示的文本片段（可为空）。"""
    utype = _update_type(update)
    if utype == "shell-output-delta":
        if isinstance(update, Mapping):
            event = _as_mapping(update.get("event"))
        else:
            event = _as_mapping(getattr(update, "event", None))
        return _chunks_from_shell_event(event)

    if utype not in ("tool-call-started", "tool-call-completed", "partial-tool-call"):
        return []

    if isinstance(update, Mapping):
        tool_call = _as_mapping(update.get("toolCall") or update.get("tool_call"))
    else:
        tool_call = _as_mapping(getattr(update, "tool_call", None))

    args = tool_call.get("args") or tool_call.get("arguments")
    name = str(tool_call.get("name") or tool_call.get("toolName") or "")
    if not _is_shell_tool(name, args):
        return []

    if utype == "tool-call-started":
        command = _extract_shell_command(tool_call)
        if command:
            return [f"\n$ {command}\n"]
        return []

    if utype == "tool-call-completed":
        out = _stdout_from_tool_result(tool_call)
        if out and not out.endswith("\n"):
            out += "\n"
        return [out] if out else []

    return []


def consume_shell_sdk_message_chunks(message: Any) -> list[str]:
    """SDK tool_call 消息（Web Agent 常见路径）→ 终端片段。"""
    msg_type = str(getattr(message, "type", "") or "")
    if msg_type != "tool_call":
        return []
    name = str(getattr(message, "name", "") or "").strip()
    args = getattr(message, "args", None)
    if not _is_shell_tool(name, args):
        return []
    status = str(getattr(message, "status", "") or "").strip().lower()
    chunks: list[str] = []
    if status in ("running", "in_progress", "started", ""):
        command = _extract_shell_command({"name": name, "args": args}) or _command_from_args(args)
        if command:
            chunks.append(f"\n$ {command}\n")
    result = getattr(message, "result", None)
    if result is not None:
        out = _stdout_from_tool_result({"result": result})
        if out and not out.endswith("\n"):
            out += "\n"
        if out:
            chunks.append(out)
    return chunks


def consume_shell_step_chunks(step: Any) -> list[str]:
    """conversation step 中的 Shell 工具结果。"""
    if getattr(step, "type", "") != "toolCall":
        return []
    message = getattr(step, "message", None)
    if not isinstance(message, Mapping):
        return []
    name = str(message.get("name") or message.get("toolName") or "")
    args = message.get("args") or message.get("arguments")
    if not _is_shell_tool(name, args):
        return []
    chunks: list[str] = []
    command = _extract_shell_command(message) or _command_from_args(args)
    if command:
        chunks.append(f"\n$ {command}\n")
    out = _stdout_from_tool_result(message)
    if out and not out.endswith("\n"):
        out += "\n"
    if out:
        chunks.append(out)
    return chunks
