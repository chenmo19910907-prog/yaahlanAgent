#!/usr/bin/env python3
"""离线验证测试用例自动导出识别逻辑。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from testcase_auto_export import (
    format_testcase_export_message,
    find_recent_testcase_files,
    is_testcase_generation_prompt,
)
from testcase_auto_export import TestcaseExportItem


def test_prompt_detection() -> None:
    assert is_testcase_generation_prompt("根据 PRD 生成测试用例")
    assert is_testcase_generation_prompt("写一版 2.4.5 用例表")
    assert not is_testcase_generation_prompt("介绍一下 platform 目录")


def test_recent_files() -> None:
    import os
    import shutil

    tmp_root = Path("/tmp/yaahlan_testcase_export_verify")
    if tmp_root.exists():
        shutil.rmtree(tmp_root)
    testcase_dir = tmp_root / "temporary_testcase"
    testcase_dir.mkdir(parents=True)
    old_file = testcase_dir / "old.md"
    new_file = testcase_dir / "new.md"
    old_file.write_text("| a | b |\n| - | - |\n| 1 | 2 |", encoding="utf-8")
    new_file.write_text("| a | b |\n| - | - |\n| 3 | 4 |", encoding="utf-8")
    now = time.time()
    os.utime(old_file, (now - 100, now - 100))
    os.utime(new_file, (now, now))
    found = find_recent_testcase_files(tmp_root, since_wall_ts=now - 5)
    assert [path.name for path in found] == ["new.md"]


def test_format_message() -> None:
    msg = format_testcase_export_message(
        [
            TestcaseExportItem(
                source=Path("x.md"),
                name="demo",
                url="https://alidocs.dingtalk.com/i/nodes/abc",
            )
        ]
    )
    assert msg.strip().startswith("https://")
    assert "目录" not in msg


def main() -> int:
    test_prompt_detection()
    print("[OK] test_prompt_detection")
    test_recent_files()
    print("[OK] test_recent_files")
    test_format_message()
    print("[OK] test_format_message")
    print("[PASS] testcase_auto_export")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
