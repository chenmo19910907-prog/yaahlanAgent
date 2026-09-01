#!/usr/bin/env python3
"""Web Agent：自动重试失败后只展示/落盘一条失败回复。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(WEB_AGENT_DIR))

from run_progress_reply import is_run_failure_reply  # noqa: E402
from web_session_store import WebSessionStore  # noqa: E402


class RetryFailureDedupTests(unittest.TestCase):
    def test_is_run_failure_reply_covers_startup_error(self) -> None:
        text = "⚠️ Agent 启动失败: internal error（已自动重试 3 次仍失败）"
        self.assertTrue(is_run_failure_reply(text))

    def test_replace_last_assistant_if_failure_overwrites_same_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = WebSessionStore(
                index_path=root / "sessions.json",
                messages_dir=root / "messages",
            )
            meta = store.create_session(title="t", owner_id="u1", owner_label="U")
            sid = meta.id
            store.append_message(sid, "user", "hello")
            store.append_message(
                sid,
                "assistant",
                "⚠️ Agent 启动失败: internal error（已自动重试 1 次仍失败）",
            )
            replaced = store.replace_last_assistant_if_failure(
                sid,
                "⚠️ Agent 启动失败: internal error（已自动重试 3 次仍失败）",
            )
            self.assertTrue(replaced)
            msgs, _ = store.get_messages(sid)
            self.assertEqual(len(msgs), 2)
            self.assertIn("3 次仍失败", msgs[-1].content)


def verify_chat_html() -> int:
    html = (WEB_AGENT_DIR / "chat.html").read_text(encoding="utf-8")
    required = [
        "function failureReplyAlreadyVisible(text)",
        "function showRunFailureReply(sessionId, shellEl, text, run = null)",
        "if (streamSettled) return;",
        "activeRuns.get(sessionId)?.failed",
        "body.startsWith('⚠️ Agent 启动失败')",
        "failRun?.failed || failureReplyAlreadyVisible",
    ]
    missing = [token for token in required if token not in html]
    if missing:
        for token in missing:
            print(f"FAIL: chat.html 缺少 {token}")
        return 1
    print("[PASS] verify_web_retry_failure_dedup chat.html")
    return 0


def main() -> int:
    code = verify_chat_html()
    if code != 0:
        return code
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RetryFailureDedupTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    print("[PASS] verify_web_retry_failure_dedup")
    return 0


if __name__ == "__main__":
    sys.exit(main())
