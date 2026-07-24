#!/usr/bin/env python3
"""dingtalk_web_sync 单测：网页验证码轮次不入 Web 历史。"""

from __future__ import annotations

import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
sys.path.insert(0, str(WEB_AGENT_DIR))
sys.path.insert(0, str(GATEWAY_DIR))

from dingtalk_web_sync import (  # noqa: E402
    should_sync_dingtalk_turn,
    sync_dingtalk_exchange,
)
from web_otp_auth import WEB_LOGIN_PHRASE  # noqa: E402
from web_session_store import WebSessionStore  # noqa: E402


class DingtalkWebSyncTests(unittest.TestCase):
    def test_should_skip_web_login_turn(self) -> None:
        self.assertFalse(
            should_sync_dingtalk_turn(
                WEB_LOGIN_PHRASE,
                "您的 Yaahlan 网页版验证码：12345678\n5 分钟内有效。",
            )
        )
        self.assertFalse(
            should_sync_dingtalk_turn(
                WEB_LOGIN_PHRASE,
                "验证码已通过私聊发送，5 分钟内有效。",
            )
        )

    def test_should_sync_normal_turn(self) -> None:
        self.assertTrue(
            should_sync_dingtalk_turn("查用户 100465989", "用户详情如下…")
        )

    def test_sync_dingtalk_exchange_skips_web_login(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WebSessionStore(
                index_path=Path(tmp) / "sessions.json",
                messages_dir=Path(tmp) / "messages",
            )
            with unittest.mock.patch(
                "dingtalk_web_sync.get_session_store", return_value=store
            ):
                ok = sync_dingtalk_exchange(
                    "dm:staff001",
                    WEB_LOGIN_PHRASE,
                    "您的 Yaahlan 网页版验证码：87654321",
                    sender_staff_id="staff001",
                )
        self.assertFalse(ok)
        self.assertEqual(len(store.list_sessions()), 0)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
