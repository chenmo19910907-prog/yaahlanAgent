#!/usr/bin/env python3
"""web_dingtalk_oauth 单测。"""

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

from web_dingtalk_oauth import (  # noqa: E402
    dingtalk_oauth_enabled,
    dingtalk_oauth_public_config,
    login_with_auth_code,
    resolve_user_from_auth_code,
)
from web_otp_auth import WebAuthUser, WebOtpAuthStore  # noqa: E402


class DingtalkOauthConfigTest(unittest.TestCase):
    def test_disabled_without_corp_id(self) -> None:
        env = {
            "WEB_AGENT_DINGTALK_OAUTH": "1",
            "DINGTALK_CLIENT_ID": "dingtest",
            "DINGTALK_CORP_ID": "",
        }
        with patch("web_dingtalk_oauth.load_env_local"):
            with patch.dict(os.environ, env, clear=True):
                self.assertFalse(dingtalk_oauth_enabled())
                cfg = dingtalk_oauth_public_config()
                self.assertFalse(cfg["enabled"])

    def test_enabled_with_client_and_corp(self) -> None:
        env = {
            "WEB_AGENT_DINGTALK_OAUTH": "1",
            "DINGTALK_CLIENT_ID": "dingtest",
            "DINGTALK_CORP_ID": "corp123",
        }
        with patch("web_dingtalk_oauth.load_env_local"):
            with patch.dict(os.environ, env, clear=True):
                self.assertTrue(dingtalk_oauth_enabled())
                cfg = dingtalk_oauth_public_config()
                self.assertTrue(cfg["enabled"])
                self.assertEqual(cfg["clientId"], "dingtest")
                self.assertEqual(cfg["corpId"], "corp123")


class DingtalkOauthResolveTest(unittest.TestCase):
    def test_resolve_user_from_auth_code_success(self) -> None:
        env = {
            "WEB_AGENT_DINGTALK_OAUTH": "1",
            "DINGTALK_CLIENT_ID": "dingtest",
            "DINGTALK_CORP_ID": "corp123",
        }
        mock_response = {
            "errcode": 0,
            "result": {"userid": "staff001", "name": "张三"},
        }

        with patch("web_dingtalk_oauth.load_env_local"):
            with patch.dict(os.environ, env, clear=True):
                with patch(
                    "web_dingtalk_oauth._get_app_access_token",
                    return_value="app-token",
                ):
                    with patch(
                        "web_dingtalk_oauth._post_topapi",
                        return_value=mock_response,
                    ) as post_mock:
                        user, err = resolve_user_from_auth_code("auth-code-xyz")
                        self.assertIsNone(err)
                        assert user is not None
                        self.assertEqual(user.staff_id, "staff001")
                        self.assertEqual(user.display_name, "张三")
                        post_mock.assert_called_once()
                        args = post_mock.call_args[0]
                        self.assertIn("access_token=app-token", args[0])
                        self.assertEqual(args[1], {"code": "auth-code-xyz"})

    def test_resolve_user_invalid_code(self) -> None:
        env = {
            "WEB_AGENT_DINGTALK_OAUTH": "1",
            "DINGTALK_CLIENT_ID": "dingtest",
            "DINGTALK_CORP_ID": "corp123",
        }
        with patch("web_dingtalk_oauth.load_env_local"):
            with patch.dict(os.environ, env, clear=True):
                with patch("web_dingtalk_oauth._get_app_access_token", return_value="app-token"):
                    with patch(
                        "web_dingtalk_oauth._post_topapi",
                        return_value={"errcode": 40078, "errmsg": "invalid code"},
                    ):
                        user, err = resolve_user_from_auth_code("bad-code")
                        self.assertIsNone(user)
                        self.assertIn("无效或已过期", err or "")


class DingtalkOauthLoginTest(unittest.TestCase):
    def test_login_with_auth_code_creates_session(self) -> None:
        env = {
            "WEB_AGENT_DINGTALK_OAUTH": "1",
            "DINGTALK_CLIENT_ID": "dingtest",
            "DINGTALK_CORP_ID": "corp123",
        }
        with tempfile.TemporaryDirectory() as tmp:
            store = WebOtpAuthStore(
                otp_path=Path(tmp) / "otp.json",
                session_path=Path(tmp) / "sessions.json",
            )
            with patch("web_dingtalk_oauth.load_env_local"):
                with patch.dict(os.environ, env, clear=True):
                    with patch("web_dingtalk_oauth.get_web_otp_store", return_value=store):
                        with patch(
                            "web_dingtalk_oauth.resolve_user_from_auth_code",
                            return_value=(
                                WebAuthUser(staff_id="staff009", display_name="李四"),
                                None,
                            ),
                        ):
                            token, user, err = login_with_auth_code("code123")
                            self.assertIsNotNone(token)
                            self.assertIsNone(err)
                            assert token and user
                            self.assertEqual(user.staff_id, "staff009")
                            validated = store.validate_session_token(token)
                            assert validated is not None
                            self.assertEqual(validated.staff_id, "staff009")


if __name__ == "__main__":
    unittest.main()
