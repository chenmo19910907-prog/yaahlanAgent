#!/usr/bin/env python3
"""离线验证执行进度心跳文案。"""

from __future__ import annotations

import sys
from unittest.mock import patch

from progress_message import (
    append_duration_footer,
    build_duration_footer,
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
    assert "预计等待约" in msg


def test_duration_footer() -> None:
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from duration_history import DurationHistoryStore

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "duration_history.json"
        store = DurationHistoryStore(path=path)
        store.record("agent:query", 90.0, status="ok")
        store.record("agent:query", 110.0, status="ok")
        with patch("progress_message.get_duration_store", return_value=store):
            footer = build_duration_footer(45.0, task_kind="agent:query")
            assert "本次耗时 45秒" in footer
            assert "同类任务通常约" in footer
            body = append_duration_footer("查询完成", 45.0, task_kind="agent:query")
            assert body.startswith("查询完成")
            assert "本次耗时 45秒" in body


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


def test_streaming_progress_status_line() -> None:
    from progress_message import build_streaming_progress_status_line

    line = build_streaming_progress_status_line(90.0, estimate_s=180.0)
    assert line == "执行中，已用时 1分30秒…"
    assert "预计还需" not in line
    assert "中断操作" not in line


def main() -> int:
    test_format_duration()
    print("[OK] test_format_duration")
    test_queue_message()
    print("[OK] test_queue_message")
    test_duration_footer()
    print("[OK] test_duration_footer")
    test_heartbeat_elapsed_only()
    print("[OK] test_heartbeat_elapsed_only")
    test_streaming_progress_status_line()
    print("[OK] test_streaming_progress_status_line")
    print("[PASS] progress_message")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
