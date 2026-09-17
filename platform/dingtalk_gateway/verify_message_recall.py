#!/usr/bin/env python3
"""离线验证消息撤回指令与 store。"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from message_recall import (
    handle_recall_command,
    is_recall_burst_command,
    is_recall_command,
)
from sent_message_store import SentMessageStore


class _FakeIncoming:
    conversation_type = "2"
    conversation_id = "cid_test"
    robot_code = "robot_test"
    sender_staff_id = "u1"
    sender_id = "u1"


class _FakeHandler:
    dingtalk_client = None


def test_recall_command_patterns() -> None:
    assert is_recall_command("撤回上一条")
    assert is_recall_command("@机器人 撤回消息")
    assert is_recall_burst_command("撤回本次回复")
    assert not is_recall_command("查用户 100465989")
    assert not is_recall_command("中断操作")


def test_sent_message_store_burst() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "keys.json"
        store = SentMessageStore(path)
        uk = "cid:user:u1"
        now = time.time()
        store.register(uk, "key-card", kind="stream_card")
        time.sleep(0.01)
        store.register(uk, "key-result", kind="markdown")
        keys = store.pop_burst_keys(uk, window_s=120.0)
        assert keys == ["key-card", "key-result"]
        assert store.recent_count(uk) == 0


def test_remove_key() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "keys.json"
        store = SentMessageStore(path)
        uk = "cid:user:u1"
        store.register(uk, "key-a", kind="stream_card")
        store.register(uk, "key-b", kind="result_card")
        assert store.remove_key(uk, "key-a")
        assert store.recent_count(uk) == 1


def test_handle_recall_empty() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "keys.json"
        store = SentMessageStore(path)
        import sent_message_store as mod

        old = mod._STORE
        mod._STORE = store
        try:
            reply = handle_recall_command(
                _FakeHandler(),
                _FakeIncoming(),
                user_key="cid:user:u1",
                text="撤回上一条",
            )
        finally:
            mod._STORE = old
        assert "暂无可撤回" in reply


def main() -> int:
    test_recall_command_patterns()
    print("[OK] test_recall_command_patterns")
    test_sent_message_store_burst()
    print("[OK] test_sent_message_store_burst")
    test_remove_key()
    print("[OK] test_remove_key")
    test_handle_recall_empty()
    print("[OK] test_handle_recall_empty")
    print("[PASS] verify_message_recall")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
