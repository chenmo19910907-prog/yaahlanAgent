#!/usr/bin/env python3
"""离线验证：批量操作进行中跳过 Agent 执行超时。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from batch_progress import (
    report_batch_progress,
    waive_agent_timeout_deadline,
)


def test_deadline_unchanged_without_batch() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        progress_dir = Path(tmp) / "batch_progress"
        with patch("batch_progress.PROGRESS_DIR", progress_dir):
            assert waive_agent_timeout_deadline(100.0, "cid:user:1") == 100.0


def test_deadline_cleared_when_batch_active() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        progress_dir = Path(tmp) / "batch_progress"
        with patch("batch_progress.PROGRESS_DIR", progress_dir):
            report_batch_progress("cid:user:1", current=1, total=5, label="查注册")
            assert waive_agent_timeout_deadline(100.0, "cid:user:1") is None


def test_deadline_cleared_stays_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        progress_dir = Path(tmp) / "batch_progress"
        with patch("batch_progress.PROGRESS_DIR", progress_dir):
            report_batch_progress("cid:user:1", current=1, total=5, label="查注册")
            assert waive_agent_timeout_deadline(None, "cid:user:1") is None


def test_no_user_key_keeps_deadline() -> None:
    assert waive_agent_timeout_deadline(100.0, None) == 100.0
    assert waive_agent_timeout_deadline(100.0, "") == 100.0


def test_batch_complete_restores_deadline_check() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        progress_dir = Path(tmp) / "batch_progress"
        with patch("batch_progress.PROGRESS_DIR", progress_dir):
            report_batch_progress("cid:user:1", current=5, total=5, label="查注册")
            assert waive_agent_timeout_deadline(100.0, "cid:user:1") == 100.0


def main() -> int:
    tests = [
        test_deadline_unchanged_without_batch,
        test_deadline_cleared_when_batch_active,
        test_deadline_cleared_stays_none,
        test_no_user_key_keeps_deadline,
        test_batch_complete_restores_deadline_check,
    ]
    for fn in tests:
        fn()
        print(f"ok {fn.__name__}")
    print(f"全部 {len(tests)} 项通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
