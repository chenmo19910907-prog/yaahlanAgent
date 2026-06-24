#!/usr/bin/env python3
"""离线验证批量结果落盘与读取。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from batch_result import (
    choose_final_reply_source,
    clear_batch_result,
    pop_batch_result,
    read_batch_result,
    save_batch_result,
)


def test_save_read_pop() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result_dir = Path(tmp) / "batch_progress"
        with patch("batch_result.RESULT_DIR", result_dir):
            key = "cid:user:WB001"
            assert read_batch_result(key) is None

            save_batch_result(key, "| 手机 | 状态 |\n| --- | --- |")
            text = read_batch_result(key)
            assert text is not None
            assert "手机" in text

            popped = pop_batch_result(key)
            assert popped is not None
            assert read_batch_result(key) is None

            clear_batch_result(key)


def test_choose_final_reply_source() -> None:
    body, source = choose_final_reply_source(
        agent_formatted="查询结果如下：第1条：手机号为133。",
        batch_result="| 手机 | 状态 |\n| --- | --- |",
    )
    assert source == "batch"
    assert body.startswith("| 手机 |")

    body2, source2 = choose_final_reply_source(
        agent_formatted="已完成统计。",
        batch_result=None,
    )
    assert source2 == "agent"
    assert body2 == "已完成统计。"


def main() -> int:
    test_save_read_pop()
    print("[OK] test_save_read_pop")
    test_choose_final_reply_source()
    print("[OK] test_choose_final_reply_source")
    print("[PASS] batch_result")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
