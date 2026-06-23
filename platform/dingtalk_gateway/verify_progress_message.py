#!/usr/bin/env python3
"""离线验证执行进度心跳文案。"""

from __future__ import annotations

import sys
from unittest.mock import patch

from progress_message import (
    build_heartbeat_message,
    build_queue_message,
    format_duration,
)
from task_session import TaskSession


def test_format_duration() -> None:
    assert format_duration(0) == "0秒"
    assert format_duration(45) == "45秒"
    assert format_duration(60) == "1分钟"
    assert format_duration(90) == "1分30秒"
    assert format_duration(3661) == "1小时1分"


def test_queue_message() -> None:
    msg = build_queue_message(2)
    assert "前面约 2 个" in msg
    assert "预计等待约 6 分钟" in msg


def test_heartbeat_elapsed_only() -> None:
    session = TaskSession()
    with patch("task_session.time.monotonic", side_effect=[1000.0, 1150.0]):
        session.begin("生成用例", conversation_id="c1", budget_s=600.0)
        msg = build_heartbeat_message(session)
    assert "仍在执行中" in msg
    assert "已执行2分30秒" in msg
    assert "Agent 执行中" not in msg
    assert "预计还需" not in msg
    assert "中断操作" in msg


def main() -> int:
    test_format_duration()
    print("[OK] test_format_duration")
    test_queue_message()
    print("[OK] test_queue_message")
    test_heartbeat_elapsed_only()
    print("[OK] test_heartbeat_elapsed_only")
    print("[PASS] progress_message")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
