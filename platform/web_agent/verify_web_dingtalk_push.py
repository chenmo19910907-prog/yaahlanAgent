#!/usr/bin/env python3
"""web_dingtalk_push 单测。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_AGENT_DIR))

from web_dingtalk_push import (  # noqa: E402
    MAX_DINGTALK_PUSH_CHARS,
    _DEFAULT_PUSH_TITLE,
    _TRUNCATE_SUFFIX,
    prepare_push_text,
    prepare_push_title,
)


class WebDingtalkPushTests(unittest.TestCase):
    def test_prepare_push_text_short_unchanged(self) -> None:
        text = "查询完成，共 3 条记录。"
        self.assertEqual(prepare_push_text(text), text)

    def test_prepare_push_text_truncates_long_body(self) -> None:
        long_text = "A" * (MAX_DINGTALK_PUSH_CHARS + 500)
        out = prepare_push_text(long_text)
        self.assertLessEqual(len(out), MAX_DINGTALK_PUSH_CHARS)
        self.assertTrue(out.endswith(_TRUNCATE_SUFFIX.strip().split("…")[-1]) or _TRUNCATE_SUFFIX in out)

    def test_prepare_push_text_empty_raises_on_push(self) -> None:
        self.assertEqual(prepare_push_text(""), "")

    def test_prepare_push_title_from_heading(self) -> None:
        text = "## 查询结果\n\n共 3 条记录。"
        self.assertEqual(prepare_push_title(text), "查询结果")

    def test_prepare_push_title_from_first_line(self) -> None:
        text = "Admin 查用户详情完成。"
        self.assertEqual(prepare_push_title(text), "Admin 查用户详情完成。")

    def test_prepare_push_title_default_when_empty(self) -> None:
        self.assertEqual(prepare_push_title(""), _DEFAULT_PUSH_TITLE)


if __name__ == "__main__":
    unittest.main()
