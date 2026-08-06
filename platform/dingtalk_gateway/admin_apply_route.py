"""钉钉快捷路由：审批 Web Agent 管理员申请。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("dingtalk-gateway")

WEB_AGENT_DIR = Path(__file__).resolve().parents[1] / "web_agent"


def handle_admin_apply_decision_message(
    *,
    text: str,
    sender_staff_id: str,
    client: Any | None = None,
) -> str:
    if str(WEB_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(WEB_AGENT_DIR))
    from web_admin_apply import handle_admin_apply_decision  # noqa: WPS433

    return handle_admin_apply_decision(
        text=text,
        sender_staff_id=sender_staff_id,
        client=client,
    )
