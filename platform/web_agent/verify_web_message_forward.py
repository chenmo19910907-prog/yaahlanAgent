#!/usr/bin/env python3
"""web_message_forward 单测。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
sys.path.insert(0, str(WEB_AGENT_DIR))
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from web_message_forward import (  # noqa: E402
    build_forward_body,
    forward_message_to_dingtalk,
)


class WebMessageForwardTests(unittest.TestCase):
    def test_build_forward_body_assistant_with_question(self) -> None:
        body = build_forward_body(
            "查询完成。",
            sender_name="张三",
            message_role="assistant",
            question_text="帮我查一下用户详情",
        )
        self.assertIn("张三", body)
        self.assertIn("Agent 回复", body)
        self.assertIn("### 提问", body)
        self.assertIn("帮我查一下用户详情", body)
        self.assertIn("查询完成。", body)

    def test_build_forward_body_strips_duration_footer(self) -> None:
        body = build_forward_body(
            "查询完成。\n\n⏱ 本次耗时 42秒（预估约 45秒：同类任务）",
            sender_name="张三",
            message_role="assistant",
        )
        self.assertIn("查询完成。", body)
        self.assertNotIn("本次耗时", body)
        self.assertNotIn("⏱", body)

    def test_build_forward_body_assistant(self) -> None:
        body = build_forward_body(
            "查询完成。",
            sender_name="张三",
            message_role="assistant",
        )
        self.assertIn("张三", body)
        self.assertIn("Agent 回复", body)
        self.assertIn("分享", body)
        self.assertIn("查询完成。", body)

    def test_build_forward_body_user(self) -> None:
        body = build_forward_body(
            "帮我查一下用户详情",
            sender_name="李四",
            message_role="user",
        )
        self.assertIn("提问", body)
        self.assertIn("帮我查一下用户详情", body)

    def test_build_forward_body_empty(self) -> None:
        self.assertEqual(build_forward_body(""), "")

    def test_forward_requires_recipients(self) -> None:
        with self.assertRaises(ValueError):
            forward_message_to_dingtalk([], "hello")

    def test_forward_requires_staff_or_group(self) -> None:
        with patch.dict(
            sys.modules,
            {
                "dingtalk_private_message": MagicMock(),
                "markdown_display": MagicMock(),
            },
        ):
            with self.assertRaises(ValueError):
                forward_message_to_dingtalk([], "hello", recipient_group_ids=[])

    def test_forward_to_group(self) -> None:
        fake_dingtalk = MagicMock()
        fake_dingtalk.send_robot_private_markdown = MagicMock()
        fake_dingtalk.send_robot_group_markdown = MagicMock()
        fake_markdown = MagicMock()
        fake_markdown.enhance_markdown_list_indent = lambda text: text
        with patch.dict(
            sys.modules,
            {
                "dingtalk_private_message": fake_dingtalk,
                "markdown_display": fake_markdown,
            },
        ):
            result = forward_message_to_dingtalk(
                [],
                "测试内容",
                recipient_group_ids=["cidTestGroup=="],
                sender_name="王五",
                message_role="assistant",
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["sent_count"], 1)
        self.assertEqual(fake_dingtalk.send_robot_group_markdown.call_count, 1)
        self.assertEqual(fake_dingtalk.send_robot_private_markdown.call_count, 0)

    def test_forward_requires_text(self) -> None:
        with self.assertRaises(ValueError):
            forward_message_to_dingtalk(["uid1"], "  ")

    def test_forward_success(self) -> None:
        fake_dingtalk = MagicMock()
        fake_dingtalk.send_robot_private_markdown = MagicMock()
        fake_markdown = MagicMock()
        fake_markdown.enhance_markdown_list_indent = lambda text: text
        with patch.dict(
            sys.modules,
            {
                "dingtalk_private_message": fake_dingtalk,
                "markdown_display": fake_markdown,
            },
        ):
            result = forward_message_to_dingtalk(
                ["staff-a", "staff-b"],
                "测试内容",
                sender_name="王五",
                message_role="assistant",
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["sent_count"], 2)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(fake_dingtalk.send_robot_private_markdown.call_count, 2)


if __name__ == "__main__":
    unittest.main()
