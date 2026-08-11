#!/usr/bin/env python3
"""web_session_context 单测。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_AGENT_DIR))

from web_session_context import (  # noqa: E402
    build_rotation_system_note,
    looks_like_pk_atm_task,
    pk_atm_prompt_hint,
    session_looks_like_pk_atm,
    should_rotate_cursor_agent,
)
from web_session_store import ChatMessage, WebSessionStore  # noqa: E402


class WebSessionContextTest(unittest.TestCase):
    def test_should_rotate_by_message_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            store = WebSessionStore(
                index_path=data / "sessions.json",
                messages_dir=data / "messages",
            )
            meta = store.create_session(owner_id="u1", owner_label="User")
            sid = meta.id
            msgs = [
                ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"m{i}")
                for i in range(80)
            ]
            with patch("web_session_context.get_session_store", return_value=store):
                store._save_messages(sid, msgs)  # noqa: SLF001
                self.assertTrue(should_rotate_cursor_agent(sid))

    def test_rotation_note_contains_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            store = WebSessionStore(
                index_path=data / "sessions.json",
                messages_dir=data / "messages",
            )
            meta = store.create_session(owner_id="u1", owner_label="User")
            sid = meta.id
            msgs = [ChatMessage(role="user", content="来一场 PK")] * 85
            with patch("web_session_context.get_session_store", return_value=store):
                store._save_messages(sid, msgs)  # noqa: SLF001
                note = build_rotation_system_note(sid)
                self.assertIn("85", note)
                self.assertIn("切换新的 Cursor Agent", note)

    def test_pk_hint(self) -> None:
        self.assertTrue(looks_like_pk_atm_task("来一场符合用例的PK"))
        self.assertTrue(looks_like_pk_atm_task("再测试一个总PK值等于10万的"))
        self.assertFalse(looks_like_pk_atm_task("查用户 100465989"))
        hint = pk_atm_prompt_hint("总PK值10万")
        self.assertIsNotNone(hint)
        assert hint is not None
        self.assertIn("pk_atm_dingtalk_sheet2_run.py", hint)
        self.assertIn("钉钉", hint)

    def test_session_pk_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            store = WebSessionStore(
                index_path=data / "sessions.json",
                messages_dir=data / "messages",
            )
            meta = store.create_session(owner_id="u1", owner_label="User")
            sid = meta.id
            msgs = [
                ChatMessage(role="user", content="来一场 PK"),
                ChatMessage(
                    role="assistant",
                    content="验收通过 pkId 01KZQJJ41RTJCPT0FMX65393EV 双方总 PK 100000",
                ),
                ChatMessage(role="user", content="有没有生成钉钉文档"),
            ]
            with patch("web_session_context.get_session_store", return_value=store):
                store._save_messages(sid, msgs)  # noqa: SLF001
                self.assertTrue(session_looks_like_pk_atm(sid))
                hint = pk_atm_prompt_hint("有没有生成钉钉文档", session_id=sid)
                self.assertIsNotNone(hint)


if __name__ == "__main__":
    unittest.main()
