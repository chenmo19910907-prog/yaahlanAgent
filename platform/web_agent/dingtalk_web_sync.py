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

from web_session_store import dingtalk_session_id, get_session_store  # noqa: E402

logger = logging.getLogger("web-agent")

_BACKFILL_DONE = False


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


def sync_dingtalk_exchange(
    dingtalk_key: str,
    user_prompt: str,
    assistant_message: str,
    *,
    sender_name: str = "",
) -> None:
    """写入一轮钉钉 user/assistant 消息到对应 Web 历史会话。"""
    if not is_sync_enabled():
        return
    key = (dingtalk_key or "").strip()
    prompt = (user_prompt or "").strip()
    reply = (assistant_message or "").strip()
    if not key or not prompt or not reply:
        return

    store = get_session_store()
    label = (sender_name or "").strip()
    meta = store.get_or_create_dingtalk_session(
        dingtalk_key=key,
        label=label,
        title_hint=prompt,
    )
    store.append_message_if_new(meta.id, "user", prompt)
    store.append_message_if_new(meta.id, "assistant", reply)
    logger.info(
        "钉钉对话已同步 Web 历史 session=%s key=%s",
        meta.id,
        key[:24],
    )


def backfill_from_conversation_store() -> int:
    """从 conversations.json 回填最近一轮（无 Web 消息记录的钉钉会话）。"""
    global _BACKFILL_DONE
    if _BACKFILL_DONE or not is_sync_enabled():
        return 0
    _BACKFILL_DONE = True
    if not CONVERSATIONS_INDEX.is_file():
        return 0
    try:
        raw = json.loads(CONVERSATIONS_INDEX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("读取 conversations.json 回填失败: %s", exc)
        return 0
    if not isinstance(raw, dict):
        return 0

    count = 0
    store = get_session_store()
    for dt_key, item in raw.items():
        if not isinstance(item, dict):
            continue
        prompt = str(item.get("prompt") or "").strip()
        reply = str(item.get("last_full_reply") or "").strip()
        if not prompt or not reply:
            continue
        session_id = dingtalk_session_id(str(dt_key))
        if store.get_messages(session_id):
            continue
        sync_dingtalk_exchange(str(dt_key), prompt, reply)
        count += 1
    if count:
        logger.info("已从 conversations.json 回填 %d 条钉钉会话", count)
    return count
