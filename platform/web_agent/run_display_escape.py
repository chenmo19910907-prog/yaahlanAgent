"""中断进度 / 终端展示：将字面量 \\n、\\t 等转为可读换行。"""

from __future__ import annotations

import ast
import re
from typing import Any

_ESCAPE_RE = re.compile(r"\\([ntr'\"\\])")
_ESCAPE_MAP = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "'": "'", "\\": "\\"}


def unescape_display_escapes(text: str, *, max_rounds: int = 6) -> str:
    body = text or ""
    if "\\" not in body:
        return body
    for _ in range(max_rounds):
        next_body = _ESCAPE_RE.sub(lambda m: _ESCAPE_MAP.get(m.group(1), m.group(0)), body)
        if next_body == body:
            break
        body = next_body
    return body


def _format_shell_result_dict(data: dict[str, Any]) -> str:
    parts: list[str] = []
    if "exitCode" in data:
        parts.append(f"exitCode: {data.get('exitCode')}")
    for key in ("stdout", "stderr"):
        raw = data.get(key)
        if raw is None:
            continue
        piece = unescape_display_escapes(str(raw))
        if piece.strip():
            parts.append(piece.rstrip())
    return "\n".join(parts).strip()


def _parse_shell_dict_at(raw: str, start: int) -> tuple[str, int] | None:
    if start < 0 or start >= len(raw):
        return None
    segment = raw[start:]
    if not segment.startswith("{'exitCode'"):
        return None
    limit = min(len(raw), start + 250_000)
    for end in range(start + 12, limit + 1):
        chunk = raw[start:end]
        if chunk.count("{") > chunk.count("}") + 2:
            continue
        try:
            parsed = ast.literal_eval(chunk)
        except (SyntaxError, ValueError):
            continue
        if isinstance(parsed, dict) and "exitCode" in parsed:
            return _format_shell_result_dict(parsed), end
    return None


def format_terminal_for_display(text: str, *, limit: int = 12_000) -> str:
    """终端 transcript：展开 Shell 结果 dict 内 stdout/stderr，并统一去转义。"""
    raw = text or ""
    if not raw.strip():
        return ""
    out: list[str] = []
    i = 0
    marker = "{'exitCode'"
    while i < len(raw):
        pos = raw.find(marker, i)
        if pos < 0:
            tail = raw[i:].strip()
            if tail:
                out.append(unescape_display_escapes(tail))
            break
        if pos > i:
            prefix = raw[i:pos].rstrip()
            if prefix:
                out.append(prefix)
        parsed = _parse_shell_dict_at(raw, pos)
        if parsed is None:
            out.append(unescape_display_escapes(raw[pos : pos + 400]))
            i = pos + 1
            continue
        block, nxt = parsed
        if block:
            out.append(block)
        i = nxt
    body = "\n".join(part for part in out if part).strip()
    if len(body) > limit:
        body = body[: limit - 1].rstrip() + "…"
    return body