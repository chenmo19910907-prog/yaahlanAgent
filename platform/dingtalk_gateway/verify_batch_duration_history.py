#!/usr/bin/env python3
"""离线验证批量耗时历史读写与 ETA 融合。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from batch_duration_history import BatchDurationHistoryStore, normalize_batch_label
from batch_progress import (
    BatchProgressState,
    estimate_batch_remaining_s,
    report_batch_progress,
)


def test_normalize_label() -> None:
    assert normalize_batch_label("  查公会 ") == "查公会"
    assert normalize_batch_label("") == "批量"


def test_record_and_estimate() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "batch_duration_history.json"
        store = BatchDurationHistoryStore(path=path)
        store.record("查公会", total=89, duration_s=44.7, status="ok")
        store.record("查公会", total=20, duration_s=10.0, status="ok")
        spi = store.estimate_sec_per_item("查公会")
        assert spi is not None
        assert 0.4 < spi < 0.6
        total_est = store.estimate_total_seconds("查公会", 89)
        assert total_est is not None
        assert 35 < total_est < 55


def test_eta_blends_history() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        hist_path = Path(tmp) / "batch_duration_history.json"
        progress_dir = Path(tmp) / "batch_progress"
        store = BatchDurationHistoryStore(path=hist_path)
        store.record("加1钻石", total=20, duration_s=20.0, status="ok")

        with patch("batch_progress.PROGRESS_DIR", progress_dir), patch(
            "batch_progress.get_batch_duration_store", return_value=store
        ):
            state = BatchProgressState(
                user_key="k",
                total=20,
                current=0,
                label="加1钻石",
                updated_at=1.0,
                started_at=1.0,
            )
            remaining = estimate_batch_remaining_s(state)
            assert remaining is not None
            assert 18 <= remaining <= 22

            state_mid = BatchProgressState(
                user_key="k",
                total=20,
                current=10,
                label="加1钻石",
                updated_at=11.0,
                started_at=1.0,
            )
            remaining_mid = estimate_batch_remaining_s(state_mid)
            assert remaining_mid is not None
            assert 8 <= remaining_mid <= 12


def test_report_records_on_complete() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        hist_path = Path(tmp) / "batch_duration_history.json"
        progress_dir = Path(tmp) / "batch_progress"
        store = BatchDurationHistoryStore(path=hist_path)
        clock = {"t": 1000.0}

        def fake_time() -> float:
            clock["t"] += 1.0
            return clock["t"]

        with patch("batch_progress.PROGRESS_DIR", progress_dir), patch(
            "batch_progress.get_batch_duration_store", return_value=store
        ), patch("batch_progress.time.time", side_effect=fake_time):
            report_batch_progress("u1", current=0, total=10, label="查公会")
            report_batch_progress("u1", current=10, total=10, label="查公会")
            report_batch_progress("u1", current=10, total=10, label="查公会")
        summary = store.summary("查公会")
        assert summary["count"] == 1


def main() -> int:
    test_normalize_label()
    print("[OK] test_normalize_label")
    test_record_and_estimate()
    print("[OK] test_record_and_estimate")
    test_eta_blends_history()
    print("[OK] test_eta_blends_history")
    test_report_records_on_complete()
    print("[OK] test_report_records_on_complete")
    print("[PASS] batch_duration_history")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
