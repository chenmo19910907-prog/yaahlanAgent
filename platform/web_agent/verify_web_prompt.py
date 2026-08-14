#!/usr/bin/env python3
"""web_prompt 规则裁剪回归测试。"""

from __future__ import annotations

import unittest

from web_prompt import _web_prompt_rule_profile, build_web_prompt


class WebPromptProfileTest(unittest.TestCase):
    def test_compact_profile_for_simple_query(self) -> None:
        self.assertEqual(_web_prompt_rule_profile("查 userId 100465989 详情"), "compact")

    def test_full_profile_for_code_modify(self) -> None:
        self.assertEqual(_web_prompt_rule_profile("修改 web_agent server.py"), "full")

    def test_new_session_query_omits_batch_rules(self) -> None:
        prompt = build_web_prompt(
            "查 userId 100465989",
            is_new_session=True,
            session_id="sess001",
        )
        self.assertIn("全自动执行", prompt)
        self.assertNotIn("批量操作进度", prompt)
        self.assertNotIn("代码修改权限", prompt)

    def test_new_session_gift_includes_gift_rules(self) -> None:
        prompt = build_web_prompt(
            "测试环境给 100465989 送礼",
            is_new_session=True,
            session_id="sess002",
        )
        self.assertIn("送礼", prompt)

    def test_continue_session_skips_full_rules(self) -> None:
        prompt = build_web_prompt(
            "继续",
            is_new_session=False,
            session_id="sess003",
        )
        self.assertIn("延续当前 Web Agent 对话", prompt)
        self.assertNotIn("你是 Yaahlan", prompt)


if __name__ == "__main__":
    unittest.main()
