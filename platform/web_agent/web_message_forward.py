"""Web Agent 消息分享至钉钉私聊/群聊。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Sequence

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from progress_message import strip_duration_footer  # noqa: E402
from web_dingtalk_push import (  # noqa: E402
    _DEFAULT_PUSH_TITLE,
    _enhance_markdown_for_dingtalk,
    prepare_push_text,
    prepare_push_title,
)

logger = logging.getLogger("web-agent")

_SHARE_TITLE = "消息分享"


def build_forward_body(
    text: str,
    *,
    sender_name: str = "",
    message_role: str = "",
    question_text: str = "",
) -> str:
    """组装分享正文（Markdown）。"""
    body = strip_duration_footer((text or "").strip())
    if not body:
        return ""
    sender = (sender_name or "").strip() or "同事"
    role_label = ""
    role = (message_role or "").strip().lower()
    if role == "user":
        role_label = "提问"
    elif role == "assistant":
        role_label = "Agent 回复"
    if role_label:
        header = f"**{sender}** 分享了一条{role_label}"
    else:
        header = f"**{sender}** 分享了以下消息"
    parts = [header]
    question = (question_text or "").strip()
    if question and role == "assistant":
        parts.extend(["", "### 提问", "", question])
    parts.extend(["", "---", "", body])
    return "\n".join(parts)


def forward_message_to_dingtalk(
    recipient_staff_ids: Sequence[str],
    text: str,
    *,
    recipient_group_ids: Sequence[str] | None = None,
    sender_name: str = "",
    message_role: str = "",
    question_text: str = "",
) -> dict[str, object]:
    """向多个钉钉用户私聊或群聊分享消息。"""
    staff_recipients = [str(item).strip() for item in recipient_staff_ids if str(item).strip()]
    group_recipients = [
        str(item).strip()
        for item in (recipient_group_ids or [])
        if str(item).strip()
    ]
    if not staff_recipients and not group_recipients:
        raise ValueError("请选择至少一位接收人或群聊")

    forward_body = build_forward_body(
        text,
        sender_name=sender_name,
        message_role=message_role,
        question_text=question_text,
    )
    if not forward_body:
        raise ValueError("消息内容为空，无法分享")

    body = prepare_push_text(_enhance_markdown_for_dingtalk(forward_body))
    if not body:
        raise ValueError("消息内容为空，无法分享")
    title = prepare_push_title(body) or _SHARE_TITLE
    if title == _DEFAULT_PUSH_TITLE:
        title = _SHARE_TITLE

    from dingtalk_private_message import (  # noqa: WPS433
        send_robot_group_markdown,
        send_robot_private_markdown,
    )

    sent: list[str] = []
    failed: list[dict[str, str]] = []
    for staff_id in staff_recipients:
        try:
            send_robot_private_markdown(staff_id, title, body)
            sent.append(f"staff:{staff_id}")
            logger.info(
                "消息已分享钉钉 staff=%s… title=%s chars=%s",
                staff_id[:12],
                title,
                len(body),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("消息分享钉钉失败 staff=%s: %s", staff_id[:12], exc)
            failed.append({"kind": "staff", "id": staff_id, "error": str(exc)})

    for conv_id in group_recipients:
        try:
            send_robot_group_markdown(conv_id, title, body)
            sent.append(f"group:{conv_id}")
            logger.info(
                "消息已分享群聊 openConversationId=%s… title=%s chars=%s",
                conv_id[:16],
                title,
                len(body),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("消息分享群聊失败 conv=%s: %s", conv_id[:16], exc)
            failed.append({"kind": "group", "id": conv_id, "error": str(exc)})

    if not sent:
        first_err = failed[0]["error"] if failed else "发送失败"
        raise RuntimeError(first_err)

    return {
        "ok": True,
        "sent_count": len(sent),
        "failed_count": len(failed),
        "failed": failed,
    }
