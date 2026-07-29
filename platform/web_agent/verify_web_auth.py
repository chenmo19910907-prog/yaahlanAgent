#!/usr/bin/env python3
"""web_auth 单测。"""

from __future__ import annotations

import os
import sys
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(WEB_AGENT_DIR))

from web_auth import (  # noqa: E402
    auth_enabled,
    auth_required_for_request,
    authorize_request,
    is_anonymous_allowed,
    is_localhost_request,
)
from web_otp_auth import current_web_user  # noqa: E402


class _FakeHandler:
    def __init__(
        self,
        headers: dict[str, str] | None = None,
        client: str = "127.0.0.1",
        path: str = "/",
    ) -> None:
        self.headers = headers or {}
        self.client_address = (client, 0)
        self.path = path
        self.response_code = 0
        self.response_headers: list[tuple[str, str]] = []
        self.body = b""
        self.wfile = BytesIO()

    def send_response(self, code: int) -> None:
        self.response_code = code

    def send_header(self, key: str, value: str) -> None:
        self.response_headers.append((key, value))

    def end_headers(self) -> None:
        self.body = self.wfile.getvalue()


class WebAuthTest(unittest.TestCase):
    def test_auth_disabled_without_env(self) -> None:
        with patch("web_auth.load_env_local", lambda: None), patch.dict(
            os.environ, {"WEB_AGENT_OTP_AUTH": "0"}, clear=True
        ):
            self.assertFalse(auth_enabled())
            handler = _FakeHandler()
            self.assertTrue(authorize_request(handler))

    def test_auth_required_when_configured(self) -> None:
        env = {
            "WEB_AGENT_OTP_AUTH": "0",
            "WEB_AGENT_AUTH_USER": "qa",
            "WEB_AGENT_AUTH_PASSWORD": "secret",
        }
        with patch("web_auth.load_env_local", lambda: None), patch.dict(os.environ, env, clear=True):
            self.assertTrue(auth_enabled())
            handler = _FakeHandler(client="8.8.8.8")
            self.assertFalse(authorize_request(handler))
            self.assertEqual(handler.response_code, 401)

    def test_auth_accepts_valid_basic(self) -> None:
        import base64

        env = {
            "WEB_AGENT_OTP_AUTH": "0",
            "WEB_AGENT_AUTH_USER": "qa",
            "WEB_AGENT_AUTH_PASSWORD": "secret",
        }
        token = base64.b64encode(b"qa:secret").decode("ascii")
        with patch("web_auth.load_env_local", lambda: None), patch.dict(os.environ, env, clear=True):
            handler = _FakeHandler(headers={"Authorization": f"Basic {token}"}, client="8.8.8.8")
            self.assertTrue(authorize_request(handler))

    def test_private_ip_skips_auth(self) -> None:
        env = {
            "WEB_AGENT_OTP_AUTH": "0",
            "WEB_AGENT_AUTH_USER": "qa",
            "WEB_AGENT_AUTH_PASSWORD": "secret",
        }
        with patch("web_auth.load_env_local", lambda: None), patch.dict(os.environ, env, clear=True):
            handler = _FakeHandler(client="172.18.125.90")
            self.assertFalse(auth_required_for_request(handler))
            self.assertTrue(authorize_request(handler))

    def test_public_ip_requires_auth(self) -> None:
        env = {
            "WEB_AGENT_OTP_AUTH": "0",
            "WEB_AGENT_AUTH_USER": "qa",
            "WEB_AGENT_AUTH_PASSWORD": "secret",
        }
        with patch("web_auth.load_env_local", lambda: None), patch.dict(os.environ, env, clear=True):
            handler = _FakeHandler(client="8.8.8.8")
            self.assertTrue(auth_required_for_request(handler))
            self.assertFalse(authorize_request(handler))

    def test_otp_guest_can_browse_dingtalk_session_messages(self) -> None:
        env = {"WEB_AGENT_OTP_AUTH": "1"}
        handler = _FakeHandler(path="/api/sessions/dt2d30ed2a75da4494/messages")
        with patch("web_auth.load_env_local", lambda: None), patch.dict(os.environ, env, clear=True):
            self.assertTrue(is_anonymous_allowed(handler, method="GET"))
            self.assertTrue(authorize_request(handler, method="GET"))

    def test_otp_guest_can_use_message_board(self) -> None:
        env = {"WEB_AGENT_OTP_AUTH": "1"}
        guest_id = "guest_" + "a" * 32
        cases = [
            ("/api/message-board", "GET"),
            ("/api/message-board", "POST"),
            (f"/api/message-board/{'b' * 32}", "DELETE"),
        ]
        with patch("web_auth.load_env_local", lambda: None), patch.dict(os.environ, env, clear=True):
            for path, method in cases:
                with self.subTest(path=path, method=method):
                    handler = _FakeHandler(
                        path=path,
                        client="8.8.8.8",
                        headers={"X-Message-Board-Guest": guest_id},
                    )
                    self.assertTrue(is_anonymous_allowed(handler, method=method))
                    self.assertTrue(authorize_request(handler, method=method))

    def test_localhost_bypasses_otp_auth(self) -> None:
        env = {"WEB_AGENT_OTP_AUTH": "1"}
        handler = _FakeHandler(client="127.0.0.1", path="/api/chat")
        with patch("web_auth.load_env_local", lambda: None), patch.dict(os.environ, env, clear=True):
            self.assertTrue(is_localhost_request(handler))
            self.assertTrue(authorize_request(handler, method="POST"))
            user = current_web_user(handler)
            assert user is not None
            self.assertEqual(user.staff_id, "admin")
            self.assertEqual(user.display_name, "admin")

    def test_lan_ip_still_requires_login_for_write(self) -> None:
        env = {"WEB_AGENT_OTP_AUTH": "1"}
        handler = _FakeHandler(client="172.18.125.90", path="/api/chat")
        with patch("web_auth.load_env_local", lambda: None), patch.dict(os.environ, env, clear=True):
            self.assertFalse(is_localhost_request(handler))
            self.assertFalse(authorize_request(handler, method="POST"))
            self.assertEqual(handler.response_code, 401)

    def test_tunnel_host_requires_auth(self) -> None:
        env = {
            "WEB_AGENT_OTP_AUTH": "0",
            "WEB_AGENT_AUTH_USER": "qa",
            "WEB_AGENT_AUTH_PASSWORD": "secret",
        }
        with patch("web_auth.load_env_local", lambda: None), patch.dict(os.environ, env, clear=True):
            handler = _FakeHandler(
                client="127.0.0.1",
                headers={"Host": "foo.trycloudflare.com"},
            )
            self.assertTrue(auth_required_for_request(handler))


if __name__ == "__main__":
    unittest.main()
