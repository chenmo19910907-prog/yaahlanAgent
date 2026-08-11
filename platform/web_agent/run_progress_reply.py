"""任务中断/超时时，将当前进度拼入 Web Agent 回复。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parents[1] / "dingtalk_gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from batch_progress import build_batch_progress_message, read_batch_progress  # noqa: E402
from batch_result import read_batch_result  # noqa: E402
from external_agent_progress import (  # noqa: E402
    build_external_agent_progress_message,
    read_external_agent_progress,
)

RETRY_HINT = "💡 原消息已回填到输入框，请检查后重试。"
INTERRUPT_HEADLINE = "⚠️ 任务已中断。"
TIMEOUT_HEADLINE = "⚠️ 任务执行超时（已超过允许时长）。"
SERVICE_RESTART_HEADLINE = "⚠️ 任务因服务重启中断"

STREAM_BODY_MAX_CHARS = 4000
BATCH_RESULT_MAX_CHARS = 6000

_LIFECYCLE_LINE_RES = (
    re.compile(r"^⏳\s*Agent\s*(启动|执行)中"),
    re.compile(r"^正在连接\s*Agent"),
    re.compile(r"^Agent\s*已启动"),
    re.compile(r"^Agent\s*执行中[…\.]?$"),
)


def is_agent_timeout_message(message: str) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return False
    if "执行超时" in (message or ""):
        return True
    return "timeout" in text and "agent" in text


def timeout_headline_from_message(message: str) -> str:
    raw = (message or "").strip()
    if raw.startswith("⚠️"):
        return raw.split("\n", 1)[0].strip()
    if "执行超时" in raw:
        return TIMEOUT_HEADLINE
    return f"⚠️ {raw}" if raw else TIMEOUT_HEADLINE


def _is_lifecycle_line(line: str) -> bool:
    text = (line or "").strip()
    if not text:
        return True
    return any(pattern.search(text) for pattern in _LIFECYCLE_LINE_RES)


def _truncate_block(text: str, *, limit: int) -> str:
    body = (text or "").strip()
    if not body:
        return ""
    if len(body) <= limit:
        return body
    return body[: limit - 1].rstrip() + "…"


def _normalize_stream_markdown(markdown: str) -> str:
    lines: list[str] = []
    for line in (markdown or "").splitlines():
        if _is_lifecycle_line(line):
            continue
        if line.strip() in {"### 思考中", "### 执行工作"} and not lines:
            lines.append(line)
            continue
        if line.strip() in {"### 思考中", "### 执行工作"} and lines and lines[-1].strip() == line.strip():
            continue
        lines.append(line)
    body = "\n".join(lines).strip()
    return _truncate_block(body, limit=STREAM_BODY_MAX_CHARS)


def _resolve_status_lines(
    user_key: str,
    *,
    batch_line: str = "",
    external_line: str = "",
) -> list[str]:
    lines: list[str] = []
    key = (user_key or "").strip()

    batch_text = (batch_line or "").strip()
    if not batch_text and key:
        state = read_batch_progress(key)
        if state is not None:
            batch_text = build_batch_progress_message(state).strip()
    if batch_text:
        lines.append(batch_text)

    external_text = (external_line or "").strip()
    if not external_text and key:
        external_text = build_external_agent_progress_message(
            read_external_agent_progress(key)
        ).strip()
    if external_text:
        lines.append(external_text)

    return lines


def build_run_stop_reply(
    headline: str,
    *,
    user_key: str = "",
    stream_markdown: str = "",
    batch_line: str = "",
    external_line: str = "",
    include_retry_hint: bool = True,
) -> str:
    """拼接中断/超时回复：标题 + 当前进度 +（可选）流式正文 + 重试提示。"""
    parts: list[str] = [(headline or "").strip() or INTERRUPT_HEADLINE]

    status_lines = _resolve_status_lines(
        user_key,
        batch_line=batch_line,
        external_line=external_line,
    )
    stream_body = _normalize_stream_markdown(stream_markdown)

    key = (user_key or "").strip()
    batch_result = ""
    if key:
        batch_result = _truncate_block(
            read_batch_result(key) or "",
            limit=BATCH_RESULT_MAX_CHARS,
        )

    progress_sections: list[str] = []
    if status_lines:
        progress_sections.append("\n".join(f"- {line}" for line in status_lines))
    if stream_body:
        progress_sections.append(stream_body)
    if batch_result:
        progress_sections.append(batch_result)

    if progress_sections:
        parts.append("## 当前进度\n\n" + "\n\n".join(progress_sections))

    if include_retry_hint:
        parts.append(RETRY_HINT)

    return "\n\n".join(part for part in parts if part.strip())
