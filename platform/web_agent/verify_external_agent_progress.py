#!/usr/bin/env python3
"""验证外部 Agent 进度上报与 Web 状态行文案。"""

from __future__ import annotations

import sys
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parents[1] / "dingtalk_gateway"
WEB_AGENT_DIR = Path(__file__).resolve().parent
for path in (GATEWAY_DIR, WEB_AGENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from external_agent_progress import (  # noqa: E402
    build_external_agent_progress_message,
    clear_external_agent_progress,
    read_external_agent_progress,
    report_external_agent_error,
    report_external_agent_querying,
)


def main() -> int:
    user_key = "web:test-external-progress"
    clear_external_agent_progress(user_key)

    report_external_agent_querying(
        user_key,
        agent_id="yaahlan_service",
        agent_label="服务端 Agent",
        message="applyAcrossRoomPk 的 MOA ServiceUrl 与 method 是什么？",
    )
    state = read_external_agent_progress(user_key)
    assert state is not None, state
    msg = build_external_agent_progress_message(state)
    assert "服务端 Agent 查询中" in msg, msg
    assert "applyAcrossRoomPk" in msg, msg

    report_external_agent_error(
        user_key,
        agent_id="yaahlan_service",
        agent_label="服务端 Agent",
        error="HTTP 401 Unauthorized",
    )
    err_msg = build_external_agent_progress_message(read_external_agent_progress(user_key))
    assert "查询失败" in err_msg, err_msg
    assert "401" in err_msg, err_msg

    clear_external_agent_progress(user_key)
    assert read_external_agent_progress(user_key) is None

    html = (WEB_AGENT_DIR / "chat.html").read_text(encoding="utf-8")
    assert "run-status-external" in html, "chat.html 缺少 external 状态样式"
    assert "run-status-phase" in html, "chat.html 缺少 phase 状态样式"
    assert "external_line" in html, "chat.html 未处理 external_line"
    assert "phase_line" in html, "chat.html 未处理 phase_line"

    print("verify_external_agent_progress: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
