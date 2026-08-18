#!/usr/bin/env python3
"""离线验证：中断/超时时将当前进度写入对话回复。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
for path in (str(GATEWAY_DIR), str(WEB_AGENT_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from batch_progress import report_batch_progress  # noqa: E402
from batch_result import save_batch_result  # noqa: E402
from external_agent_progress import report_external_agent_querying  # noqa: E402
from run_progress_reply import (  # noqa: E402
    build_run_stop_reply,
    is_agent_timeout_message,
)


class RunProgressReplyTests(unittest.TestCase):
    def test_timeout_detection(self) -> None:
        self.assertTrue(is_agent_timeout_message("Agent 执行超时（>600s），可发「重新执行」重试"))
        self.assertFalse(is_agent_timeout_message("connection refused"))

    def test_build_reply_includes_batch_stream_and_result(self) -> None:
        user_key = "web:test-progress-reply"
        with tempfile.TemporaryDirectory() as tmp:
            progress_dir = Path(tmp) / "batch_progress"
            external_dir = Path(tmp) / "external_agent_progress"
            with patch("batch_progress.PROGRESS_DIR", progress_dir), patch(
                "batch_result.RESULT_DIR", progress_dir
            ), patch("external_agent_progress.PROGRESS_DIR", external_dir):
                report_batch_progress(user_key, current=3, total=10, label="发钻石")
                save_batch_result(user_key, "| userId | 状态 |\n| --- | --- |\n| 1 | ok |")
                report_external_agent_querying(
                    user_key,
                    agent_id="svc",
                    agent_label="服务端 Agent",
                    message="查 MOA",
                )
                body = build_run_stop_reply(
                    "⚠️ 任务执行超时（已超过允许时长）。",
                    user_key=user_key,
                    stream_markdown="### 思考中\n\n正在批量查 userId…\n\n### 执行工作\n- Shell MOA",
                )

                self.assertIn("## 当前进度", body)
                self.assertIn("3/10", body)
                self.assertIn("服务端 Agent 查询中", body)
                self.assertIn("### 思考中", body)
                self.assertIn("Shell MOA", body)
                self.assertIn("| userId | 状态 |", body)
                self.assertIn("原消息已回填", body)

    def test_build_reply_without_progress_keeps_headline(self) -> None:
        body = build_run_stop_reply("⚠️ 任务已中断。")
        self.assertIn("⚠️ 任务已中断。", body)
        self.assertNotIn("## 当前进度", body)

    def test_stale_batch_result_not_shown_without_current_run_activity(self) -> None:
        user_key = "web:test-stale-result"
        with tempfile.TemporaryDirectory() as tmp:
            progress_dir = Path(tmp) / "batch_progress"
            with patch("batch_progress.PROGRESS_DIR", progress_dir), patch(
                "batch_result.RESULT_DIR", progress_dir
            ):
                save_batch_result(user_key, "第5-7步完成 | 表：2026-08-06家族PK数据测试")
                body = build_run_stop_reply("⚠️ 任务已中断。", user_key=user_key)
                self.assertNotIn("## 当前进度", body)
                self.assertNotIn("家族PK", body)


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RunProgressReplyTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("[PASS] run_progress_reply")


if __name__ == "__main__":
    main()
