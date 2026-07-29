#!/usr/bin/env python3
"""web_otp_auth 单测。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(WEB_AGENT_DIR))

from web_otp_auth import (  # noqa: E402
    WEB_LOGIN_PHRASE,
    WebOtpAuthStore,
    is_public_auth_path,
    is_web_login_request,
)


class WebOtpAuthTest(unittest.TestCase):
    def test_login_phrase_match(self) -> None:
        self.assertTrue(is_web_login_request(WEB_LOGIN_PHRASE))
        self.assertTrue(is_web_login_request("  请求访问 Yaahlan 智能工具 Agent  "))
        self.assertFalse(is_web_login_request("网页登录"))

    def test_login_public_static_paths(self) -> None:
        self.assertTrue(is_public_auth_path("/login.html"))
        self.assertTrue(is_public_auth_path("/theme.js"))
        self.assertTrue(is_public_auth_path("/dingtalk_oauth.js"))
        self.assertTrue(is_public_auth_path("/api/auth/status"))
        self.assertFalse(is_public_auth_path("/chat.html"))

    def test_issue_verify_and_invalidate_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            otp_path = Path(tmp) / "otp.json"
            session_path = Path(tmp) / "sessions.json"
            store = WebOtpAuthStore(otp_path=otp_path, session_path=session_path)

            token1, user1, err1 = store.verify_otp_and_create_session("12345678")
            self.assertIsNone(token1)
            self.assertIsNone(user1)
            self.assertTrue(err1)

            code, err = store.issue_otp("staff001", display_name="测试用户")
            self.assertIsNotNone(code)
            self.assertIsNone(err)
            assert code is not None
            self.assertEqual(len(code), 8)

            token, user, login_err = store.verify_otp_and_create_session(code)
            self.assertIsNotNone(token)
            self.assertIsNone(login_err)
            assert token and user
            self.assertEqual(user.staff_id, "staff001")
            self.assertEqual(store.validate_session_token(token).staff_id, "staff001")

            code2, err2 = store.issue_otp("staff001", display_name="测试用户")
            self.assertIsNotNone(code2)
            self.assertIsNone(store.validate_session_token(token))
            assert code2 is not None
            token2, user2, login_err2 = store.verify_otp_and_create_session(code2)
            self.assertIsNotNone(token2)
            self.assertIsNone(login_err2)
            assert token2 and user2
            self.assertEqual(user2.staff_id, "staff001")

    def test_rate_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WebOtpAuthStore(
                otp_path=Path(tmp) / "otp.json",
                session_path=Path(tmp) / "sessions.json",
            )
            code1, err1 = store.issue_otp("staff002")
            self.assertIsNotNone(code1)
            self.assertIsNone(err1)
            code2, err2 = store.issue_otp("staff002")
            self.assertIsNone(code2)
            self.assertIsNotNone(err2)


class WebAuthIntegrationTest(unittest.TestCase):
    def test_otp_auth_blocks_write_without_cookie(self) -> None:
        from io import BytesIO

        from web_auth import authorize_request

        class Handler:
            path = "/api/chat"
            headers = {}
            client_address = ("127.0.0.1", 0)
            response_code = 0
            response_headers: list[tuple[str, str]] = []
            wfile = BytesIO()

            def send_response(self, code: int) -> None:
                self.response_code = code

            def send_header(self, key: str, value: str) -> None:
                self.response_headers.append((key, value))

            def end_headers(self) -> None:
                pass

        with patch.dict(os.environ, {"WEB_AGENT_OTP_AUTH": "1"}, clear=False):
            handler = Handler()
            self.assertFalse(authorize_request(handler, method="POST"))
            self.assertEqual(handler.response_code, 401)

    def test_otp_auth_allows_anonymous_browse(self) -> None:
        from io import BytesIO

        from web_auth import authorize_request

        class Handler:
            def __init__(self, path: str) -> None:
                self.path = path
                self.headers = {}
                self.client_address = ("127.0.0.1", 0)
                self.response_code = 0
                self.response_headers: list[tuple[str, str]] = []
                self.wfile = BytesIO()

            def send_response(self, code: int) -> None:
                self.response_code = code

            def send_header(self, key: str, value: str) -> None:
                self.response_headers.append((key, value))

            def end_headers(self) -> None:
                pass

        with patch.dict(os.environ, {"WEB_AGENT_OTP_AUTH": "1"}, clear=False):
            for path in ("/", "/chat.html", "/api/meta", "/api/sessions"):
                handler = Handler(path)
                self.assertTrue(authorize_request(handler, method="GET"), path)


if __name__ == "__main__":
    unittest.main()
