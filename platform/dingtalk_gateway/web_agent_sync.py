"""钉钉网关 → Web Agent 历史会话同步桥接。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger("dingtalk-gateway")

WEB_AGENT_DIR = Path(__file__).resolve().parents[1] / "web_agent"


def sync_exchange_to_web_agent(
    dingtalk_key: str,
    user_prompt: str,
    assistant_message: str,
    *,
    sender_name: str = "",
) -> None:
    try:
        if str(WEB_AGENT_DIR) not in sys.path:
            sys.path.insert(0, str(WEB_AGENT_DIR))
        from dingtalk_web_sync import sync_dingtalk_exchange  # noqa: WPS433

        sync_dingtalk_exchange(
            dingtalk_key,
            user_prompt,
            assistant_message,
            sender_name=sender_name,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("同步 Web Agent 历史失败 key=%s: %s", dingtalk_key[:24], exc)
