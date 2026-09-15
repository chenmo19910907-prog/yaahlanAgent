#!/usr/bin/env python3
"""小程序 web-view 会话桥接单测。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(WEB_AGENT_DIR))

from web_otp_auth import WebOtpAuthStore  # noqa: E402


class MiniappSessionBridgeTest(unittest.TestCase):
    def test_session_token_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WebOtpAuthStore(
                otp_path=Path(tmp) / "otp.json",
                session_path=Path(tmp) / "sessions.json",
            )
            token, user, err = store.create_session_for_staff(
                "staff001",
                display_name="测试",
            )
            self.assertIsNone(err)
            assert token and user
            validated = store.validate_session_token(token)
            assert validated is not None
            self.assertEqual(validated.staff_id, "staff001")
            self.assertEqual(validated.display_name, "测试")

    def test_invalid_session_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WebOtpAuthStore(
                otp_path=Path(tmp) / "otp.json",
                session_path=Path(tmp) / "sessions.json",
            )
            self.assertIsNone(store.validate_session_token("not-a-real-token"))


if __name__ == "__main__":
    unittest.main()
