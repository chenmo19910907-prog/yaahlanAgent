#!/usr/bin/env python3
"""离线验证逻辑链耗时预估。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from task_chain_estimate import (
    analyze_task_chain,
    estimate_batch_sec_per_item,
    save_batch_task_context,
)


def test_batch_diamond_chain() -> None:
    chain = analyze_task_chain(
        "给 13311111111 13311111112 13311111113 发钻石",
        batch_label="发钻石",
        batch_total=3,
    )
    assert chain.batch_count == 3
    assert "查手机号" in chain.summary
    assert chain.total_seconds > 30


def test_registry_chain() -> None:
    chain = analyze_task_chain("所有能力遍历一下，按照正确的分类分配")
    assert "registry" in chain.summary or "改 registry" in chain.summary
    assert chain.total_seconds >= 5


def test_batch_sec_per_item_with_context() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ctx_dir = Path(tmp) / "ctx"
        with patch("task_chain_estimate.CONTEXT_DIR", ctx_dir):
            save_batch_task_context("web:test", "10 个手机号发钻石")
            spi = estimate_batch_sec_per_item("发钻石", user_key="web:test")
            assert spi is not None
            assert 10 <= spi <= 14


def test_moa_check_fast() -> None:
    chain = analyze_task_chain("MOA检查", task_kind="fast:moa_check")
    assert chain.total_seconds <= 5


def main() -> int:
    test_batch_diamond_chain()
    print("[OK] test_batch_diamond_chain")
    test_registry_chain()
    print("[OK] test_registry_chain")
    test_batch_sec_per_item_with_context()
    print("[OK] test_batch_sec_per_item_with_context")
    test_moa_check_fast()
    print("[OK] test_moa_check_fast")
    print("[PASS] task_chain_estimate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
