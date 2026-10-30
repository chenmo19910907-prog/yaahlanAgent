#!/usr/bin/env python3
"""离线验证批量操作项数上限。"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from batch_operation_guard import (
    NON_ADMIN_MAX_BATCH_ITEMS,
    assert_batch_total_allowed,
    estimate_batch_item_count,
    resolve_batch_operation_denial,
)
from batch_progress import report_batch_progress


def test_estimate_and_denial() -> None:
    assert estimate_batch_item_count("给 13311111111 13311111112 13311111113 加钻") == 3
    assert estimate_batch_item_count("13311111111到13311112110 互关") == 1000
    assert resolve_batch_operation_denial(
        "批量操作任务增加个上限，非管理员1000次",
        is_admin_user=False,
    ) is None
    msg = resolve_batch_operation_denial(
        "给 " + " ".join(f"1331111{i:04d}" for i in range(1001)) + " 各加1钻",
        is_admin_user=False,
    )
    assert msg is not None
    assert str(NON_ADMIN_MAX_BATCH_ITEMS) in msg
    assert (
        resolve_batch_operation_denial(
            "给 " + " ".join(f"1331111{i:04d}" for i in range(1001)) + " 各加1钻",
            is_admin_user=True,
        )
        is None
    )


def test_report_batch_progress_enforces() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        progress_dir = Path(tmp) / "batch_progress"
        with patch("batch_progress.PROGRESS_DIR", progress_dir):
            os.environ["WEB_AGENT_CALLER_STAFF_ID"] = "not-an-admin-id"
            with patch(
                "batch_operation_guard.is_admin",
                return_value=False,
            ):
                try:
                    report_batch_progress("web:test", current=0, total=1001, label="x")
                    raise AssertionError("expected ValueError")
                except ValueError as exc:
                    assert str(NON_ADMIN_MAX_BATCH_ITEMS) in str(exc)
                report_batch_progress("web:test", current=0, total=1000, label="x")
            with patch(
                "batch_operation_guard.is_admin",
                return_value=True,
            ):
                report_batch_progress("web:test", current=0, total=5000, label="x")


def main() -> int:
    test_estimate_and_denial()
    test_report_batch_progress_enforces()
    print("[PASS] batch_operation_guard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
