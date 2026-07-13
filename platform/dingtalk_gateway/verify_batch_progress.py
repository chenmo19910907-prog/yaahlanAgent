#!/usr/bin/env python3
"""离线验证批量操作进度读写与推送策略。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from batch_progress import (
    BatchProgressState,
    build_batch_progress_message,
    clear_batch_progress,
    estimate_batch_remaining_s,
    format_batch_eta_remaining,
    is_batch_progress_active,
    read_batch_progress,
    report_batch_progress,
    should_push_batch_progress,
)


def test_report_and_read() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        progress_dir = Path(tmp) / "batch_progress"
        with patch("batch_progress.PROGRESS_DIR", progress_dir):
            report_batch_progress("cid:user:WB001", current=0, total=5, label="查注册")
            state = read_batch_progress("cid:user:WB001")
            assert state is not None
            assert state.current == 0
            assert state.total == 5
            assert state.label == "查注册"

            report_batch_progress(
                "cid:user:WB001",
                current=3,
                total=5,
                label="查注册",
                detail="13311111113",
            )
            state = read_batch_progress("cid:user:WB001")
            assert state is not None
            assert state.current == 3
            assert state.detail == "13311111113"

            clear_batch_progress("cid:user:WB001")
            assert read_batch_progress("cid:user:WB001") is None


def test_message_format() -> None:
    msg = build_batch_progress_message(
        BatchProgressState(
            user_key="k",
            total=11,
            current=3,
            label="发钻石",
            detail="13311111120",
            updated_at=30.0,
            started_at=0.0,
        )
    )
    assert "3/11" in msg
    assert "已完成" in msg
    assert "项" in msg
    assert "发钻石" in msg
    assert "当前 13311111120" in msg
    assert "预计还需" in msg

    done = build_batch_progress_message(
        BatchProgressState(user_key="k", total=11, current=11, label="发钻石")
    )
    assert "完成" in done
    assert "共 11 项" in done
    assert "结果见下一条" not in done
    assert "预计还需" not in done


def test_eta_cap() -> None:
    # 100 项才完成 1 项，每项 10s → 剩余约 990s > 3 分钟
    state = BatchProgressState(
        user_key="k",
        total=100,
        current=1,
        label="查号",
        updated_at=1010.0,
        started_at=1000.0,
    )
    remaining = estimate_batch_remaining_s(state)
    assert remaining is not None and remaining > 180
    eta = format_batch_eta_remaining(remaining)
    assert eta == "，预计还需3分钟以上"

    short = format_batch_eta_remaining(45.0)
    assert short == "，预计还需约 45秒"

    assert format_batch_eta_remaining(0.0) == "，即将完成"
    assert format_batch_eta_remaining(0.4) == "，即将完成"
    assert "预计还需0秒" not in format_batch_eta_remaining(0.4)

    msg = build_batch_progress_message(state)
    assert "3分钟以上" in msg


def test_eta_at_start() -> None:
    state = BatchProgressState(
        user_key="k",
        total=20,
        current=0,
        label="加钻",
        updated_at=1.0,
        started_at=1.0,
    )
    msg = build_batch_progress_message(state)
    assert "0/20" in msg
    assert "已完成" in msg
    assert "预计还需约 20秒" in msg


def test_push_policy() -> None:
    state = BatchProgressState(user_key="k", total=11, current=1, label="x")
    assert should_push_batch_progress(state, last_pushed_current=0, last_push_at=0.0, now=1.0)

    state2 = BatchProgressState(user_key="k", total=11, current=5, label="x")
    assert not should_push_batch_progress(
        state2, last_pushed_current=1, last_push_at=100.0, now=120.0
    )
    assert should_push_batch_progress(
        state2, last_pushed_current=1, last_push_at=100.0, now=130.0
    )

    state_done = BatchProgressState(user_key="k", total=5, current=5, label="x")
    assert should_push_batch_progress(
        state_done, last_pushed_current=4, last_push_at=0.0, now=1.0
    )


def test_batch_active() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        progress_dir = Path(tmp) / "batch_progress"
        with patch("batch_progress.PROGRESS_DIR", progress_dir):
            assert not is_batch_progress_active("cid:user:WB001")
            report_batch_progress("cid:user:WB001", current=0, total=10, label="x")
            assert is_batch_progress_active("cid:user:WB001")
            report_batch_progress("cid:user:WB001", current=10, total=10, label="x")
            assert not is_batch_progress_active("cid:user:WB001")
            report_batch_progress("cid:user:WB001", current=1, total=2, label="x")
            assert not is_batch_progress_active("cid:user:WB001")
            assert read_batch_progress("cid:user:WB001") is None


def test_non_batch_skips_progress_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        progress_dir = Path(tmp) / "batch_progress"
        with patch("batch_progress.PROGRESS_DIR", progress_dir):
            report_batch_progress("cid:user:WB001", current=0, total=5, label="x")
            assert read_batch_progress("cid:user:WB001") is not None
            state = report_batch_progress("cid:user:WB001", current=2, total=2, label="砸蛋")
            assert state is None
            assert read_batch_progress("cid:user:WB001") is None


def test_push_policy_rejects_small_batch() -> None:
    state_small = BatchProgressState(user_key="k", total=2, current=2, label="砸蛋")
    assert not should_push_batch_progress(
        state_small, last_pushed_current=0, last_push_at=0.0, now=1.0
    )


def main() -> int:
    test_report_and_read()
    print("[OK] test_report_and_read")
    test_message_format()
    print("[OK] test_message_format")
    test_eta_cap()
    print("[OK] test_eta_cap")
    test_eta_at_start()
    print("[OK] test_eta_at_start")
    test_push_policy()
    print("[OK] test_push_policy")
    test_batch_active()
    print("[OK] test_batch_active")
    test_non_batch_skips_progress_file()
    print("[OK] test_non_batch_skips_progress_file")
    test_push_policy_rejects_small_batch()
    print("[OK] test_push_policy_rejects_small_batch")
    print("[PASS] batch_progress")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
