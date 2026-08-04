"""Web Agent 执行完成后向钉钉私聊推送结果。"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger("web-agent")

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"

MAX_DINGTALK_PUSH_CHARS = 12000
_DEFAULT_PUSH_TITLE = "Web Agent 结果"
_TRUNCATE_SUFFIX = "\n\n…（内容过长，完整结果请查看 Web Agent）"
_HEADING_RE = re.compile(r"^#{1,6}\s+")


def prepare_push_text(text: str, *, max_chars: int = MAX_DINGTALK_PUSH_CHARS) -> str:
    """截断过长正文，避免超出钉钉私聊限制。"""
    body = (text or "").strip()
    limit = max(200, int(max_chars))
    if len(body) <= limit:
        return body
    keep = limit - len(_TRUNCATE_SUFFIX)
    if keep < 1:
        return body[:limit]
    return body[:keep].rstrip() + _TRUNCATE_SUFFIX


def prepare_push_title(text: str, *, max_chars: int = 24) -> str:
    """从 Markdown 正文提取钉钉卡片标题。"""
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _HEADING_RE.match(stripped):
            heading = _HEADING_RE.sub("", stripped).strip()
            if heading:
                stripped = heading
        one_line = stripped.replace("\n", " ")
        if len(one_line) > max_chars:
            return one_line[: max_chars - 1] + "…"
        return one_line
    return _DEFAULT_PUSH_TITLE


def _enhance_markdown_for_dingtalk(text: str) -> str:
    if str(GATEWAY_DIR) not in sys.path:
        sys.path.insert(0, str(GATEWAY_DIR))
    from markdown_display import enhance_markdown_list_indent  # noqa: WPS433

    return enhance_markdown_list_indent(text)


def push_web_result_to_dingtalk(staff_id: str, text: str) -> None:
    """向指定用户钉钉私聊发送 Web Agent 最终结果（Markdown）。"""
    uid = (staff_id or "").strip()
    if not uid:
        raise ValueError("缺少钉钉用户标识，无法推送")
    body = prepare_push_text(_enhance_markdown_for_dingtalk(text))
    if not body:
        raise ValueError("结果为空，无需推送")
    title = prepare_push_title(body)

    if str(GATEWAY_DIR) not in sys.path:
        sys.path.insert(0, str(GATEWAY_DIR))
    from dingtalk_private_message import send_robot_private_markdown  # noqa: WPS433

    send_robot_private_markdown(uid, title, body)
    logger.info(
        "Web 结果已推送钉钉(Markdown) staff=%s… title=%s chars=%s",
        uid[:12],
        title,
        len(body),
    )
