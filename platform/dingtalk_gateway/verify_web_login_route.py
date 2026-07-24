#!/usr/bin/env python3
"""网页登录口令路由单测。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

GATEWAY_DIR = Path(__file__).resolve().parent
WEB_AGENT_DIR = GATEWAY_DIR.parent / "web_agent"
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(WEB_AGENT_DIR))

from route_patterns import is_likely_fast_route, is_web_login_request  # noqa: E402
from web_login_route import handle_web_login_request  # noqa: E402
from web_otp_auth import WebOtpAuthStore  # noqa: E402


def test_route_patterns() -> None:
    phrase = "请求访问Yaahlan 智能工具 Agent"
    assert is_web_login_request(phrase)
    assert is_likely_fast_route(phrase)
    assert not is_web_login_request("帮助")


def test_group_request_sends_dm_only() -> None:
    sent: list[tuple[str, str]] = []

    def fake_send(staff_id: str, text: str, *, client=None) -> None:  # noqa: ARG001
        sent.append((staff_id, text))

    with tempfile.TemporaryDirectory() as tmp:
        store = WebOtpAuthStore(
            otp_path=Path(tmp) / "otp.json",
            session_path=Path(tmp) / "sessions.json",
        )
        with patch("web_login_route._import_otp") as import_otp:
            import_otp.return_value = ("请求访问Yaahlan 智能工具 Agent", lambda: store, None)
            mock_dm = MagicMock()
            mock_dm.send_robot_private_text = fake_send
            with patch.dict(sys.modules, {"dingtalk_private_message": mock_dm}):
                reply, dm_ok = handle_web_login_request(
                    sender_staff_id="staff001",
                    sender_name="测试",
                    conversation_type="2",
                )
        assert dm_ok is True
        assert len(sent) == 1
        assert sent[0][0] == "staff001"
        assert "验证码：" in sent[0][1]
        assert "验证码已通过私聊发送" in reply
        assert sent[0][1].split("验证码：")[1][:8] not in reply


def test_dm_request_replies_in_thread() -> None:
    mock_dm = MagicMock()
    with tempfile.TemporaryDirectory() as tmp:
        store = WebOtpAuthStore(
            otp_path=Path(tmp) / "otp.json",
            session_path=Path(tmp) / "sessions.json",
        )
        with patch("web_login_route._import_otp") as import_otp:
            import_otp.return_value = ("请求访问Yaahlan 智能工具 Agent", lambda: store, None)
            with patch.dict(sys.modules, {"dingtalk_private_message": mock_dm}):
                reply, dm_ok = handle_web_login_request(
                    sender_staff_id="staff002",
                    conversation_type="1",
                )
    mock_dm.send_robot_private_text.assert_not_called()
    assert dm_ok is True
    assert "验证码：" in reply
    assert "已通过私聊发送" not in reply


def main() -> int:
    test_route_patterns()
    test_group_request_sends_dm_only()
    test_dm_request_replies_in_thread()
    print("[PASS] web_login_route")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
