"""将钉钉机器人对话同步到 Web Agent 历史会话。"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
CONFIG_PATH = WEB_AGENT_DIR / "config.json"
CONVERSATIONS_INDEX = GATEWAY_DIR / "data" / "conversations.json"

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from web_otp_auth import is_web_login_request  # noqa: E402
from web_session_store import (  # noqa: E402
    ChatMessage,
    _turn_already_synced,
    dingtalk_session_id,
    get_session_store,
    parse_dingtalk_user_id,
)

logger = logging.getLogger("web-agent")

_OTP_REPLY_MARKERS = (
    "Yaahlan 网页版验证码",
    "验证码已通过私聊发送",
)


def should_sync_dingtalk_turn(user_prompt: str, assistant_message: str = "") -> bool:
    """网页验证码口令及其回复不同步到 Web 历史（避免明文验证码落库）。"""
    prompt = (user_prompt or "").strip()
    reply = (assistant_message or "").strip()
    if is_web_login_request(prompt):
        return False
    if reply and any(marker in reply for marker in _OTP_REPLY_MARKERS):
        return False
    return True


def is_sync_enabled() -> bool:
    import os

    raw = os.environ.get("DINGTALK_SYNC_WEB_HISTORY", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if not CONFIG_PATH.is_file():
        return True
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    if not isinstance(data, dict):
        return True
    value = data.get("sync_dingtalk_chat")
    if isinstance(value, bool):
        return value
    return True


def turn_already_synced(
    messages: list[ChatMessage], prompt: str, reply: str = ""
) -> bool:
    """该轮 user 提问是否已有相同 assistant 回复（避免重复同步）。"""
    return _turn_already_synced(messages, prompt, reply)


def sync_dingtalk_exchange(
    dingtalk_key: str,
    user_prompt: str,
    assistant_message: str,
    *,
    sender_name: str = "",
    sender_staff_id: str = "",
) -> bool:
    """写入一轮钉钉 user/assistant 消息到对应 Web 历史会话。"""
    if not is_sync_enabled():
        return False
    key = (dingtalk_key or "").strip()
    prompt = (user_prompt or "").strip()
    reply = (assistant_message or "").strip()
    if not key or not prompt or not reply:
        return False
    if not should_sync_dingtalk_turn(prompt, reply):
        logger.debug("跳过网页验证码轮次同步 key=%s", key[:24])
        return False

    store = get_session_store()
    store.reload_from_disk()
    label = (sender_name or "").strip()
    owner_id = (sender_staff_id or "").strip() or parse_dingtalk_user_id(key)
    meta = store.get_or_create_dingtalk_session(
        dingtalk_key=key,
        label=label,
        title_hint=prompt,
        owner_id=owner_id,
    )
    messages = store.get_messages(meta.id)
    if turn_already_synced(messages, prompt, reply):
        return False
    if not store.upsert_dingtalk_turn(meta.id, prompt, reply):
        return False
    logger.info(
        "钉钉对话已同步 Web 历史 session=%s key=%s msgs=%s",
        meta.id,
        key[:24],
        len(store.get_messages(meta.id)),
    )
    return True


def sync_all_from_conversation_store() -> int:
    """增量：从 conversations.json 补同步尚未入库的钉钉轮次。"""
    if not is_sync_enabled():
        return 0
    if not CONVERSATIONS_INDEX.is_file():
        return 0
    try:
        raw = json.loads(CONVERSATIONS_INDEX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("读取 conversations.json 同步失败: %s", exc)
        return 0
    if not isinstance(raw, dict):
        return 0

    count = 0
    for dt_key, item in raw.items():
        if not isinstance(item, dict):
            continue
        prompt = str(item.get("prompt") or "").strip()
        reply = str(item.get("last_full_reply") or "").strip()
        if not prompt or not reply:
            continue
        if not should_sync_dingtalk_turn(prompt, reply):
            continue
        if sync_dingtalk_exchange(str(dt_key), prompt, reply):
            count += 1
    if count:
        logger.info("已从 conversations.json 增量同步 %d 轮钉钉对话", count)
    return count


# 兼容旧名
backfill_from_conversation_store = sync_all_from_conversation_store
