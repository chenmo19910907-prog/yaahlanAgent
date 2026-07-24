"""钉钉口令签发网页版验证码。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("dingtalk-gateway")

WEB_AGENT_DIR = Path(__file__).resolve().parents[1] / "web_agent"


def _import_otp():
    if str(WEB_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(WEB_AGENT_DIR))
    from web_otp_auth import WEB_LOGIN_PHRASE, get_web_otp_store, is_web_login_request  # noqa: WPS433

    return WEB_LOGIN_PHRASE, get_web_otp_store, is_web_login_request


def _otp_private_body(code: str) -> str:
    return (
        f"您的 Yaahlan 网页版验证码：{code}\n"
        f"5 分钟内有效。请在网页登录页输入该验证码。\n"
        f"重新获取验证码后，此前网页登录将失效。"
    )


def _group_ack_without_code(*, phrase: str) -> str:
    return (
        "验证码已通过私聊发送，5 分钟内有效。\n"
        "此前网页登录已失效，请在登录页输入新验证码。\n"
        f"（若未收到，请确认已与机器人有过单聊，或再次发送：{phrase}）"
    )


def handle_web_login_request(
    *,
    sender_staff_id: str,
    sender_name: str = "",
    conversation_type: str | None = None,
    client: Any | None = None,
) -> tuple[str, bool]:
    """签发验证码；群内仅私聊发码，单聊直接在会话回复。返回 (会话回复, 私聊是否成功)。"""
    phrase, get_store, _ = _import_otp()
    staff_id = (sender_staff_id or "").strip()
    if not staff_id:
        return "无法识别你的钉钉身份，请用企业账号 @机器人 后再试。", False

    store = get_store()
    code, err = store.issue_otp(staff_id, display_name=sender_name)
    if not code:
        return err or "验证码签发失败，请稍后重试。", False

    private_body = _otp_private_body(code)
    from_group = (conversation_type or "").strip() == "2"

    if not from_group:
        return private_body, True

    try:
        from dingtalk_private_message import send_robot_private_text

        send_robot_private_text(staff_id, private_body, client=client)
    except Exception as exc:  # noqa: BLE001
        logger.exception("网页验证码私聊发送失败 staff=%s", staff_id[:12])
        return f"验证码已生成，但私聊发送失败：{exc}", False

    return _group_ack_without_code(phrase=phrase), True
