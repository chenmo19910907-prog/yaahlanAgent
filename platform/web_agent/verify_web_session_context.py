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
    build_continue_context_note,
    build_rotation_system_note,
    looks_like_pk_atm_task,
    looks_like_vague_follow_up,
    pk_atm_prompt_hint,
    session_looks_like_pk_atm,
    should_rotate_cursor_agent,
)
from web_session_store import ChatMessage, WebSessionStore  # noqa: E402


def _seed_messages(store: WebSessionStore, sid: str, msgs: list[ChatMessage]) -> None:
    store._save_messages(sid, msgs)  # noqa: SLF001
    with store._lock:
        store._sessions[sid].message_count = len(msgs)


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
                _seed_messages(store, sid, msgs)
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
                _seed_messages(store, sid, msgs)
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

    def test_vague_follow_up_detection(self) -> None:
        self.assertTrue(looks_like_vague_follow_up("能做成工作流吗"))
        self.assertTrue(looks_like_vague_follow_up("把这个优化一下吧"))
        self.assertTrue(looks_like_vague_follow_up("再分析一下"))
        self.assertFalse(
            looks_like_vague_follow_up("线上环境13311111111添加vip8"),
        )
        self.assertFalse(
            looks_like_vague_follow_up("查 userId 100465989 详情"),
        )

    def test_continue_context_note_for_vague_follow_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            store = WebSessionStore(
                index_path=data / "sessions.json",
                messages_dir=data / "messages",
            )
            meta = store.create_session(owner_id="u1", owner_label="User")
            sid = meta.id
            msgs = [
                ChatMessage(
                    role="user",
                    content="prd2.6.1版本家族怪兽挑战，分析一下这个玩法是什么",
                ),
                ChatMessage(
                    role="assistant",
                    content="家族怪兽挑战是 v2.6.1 家族向 PVE 打怪玩法。",
                ),
            ]
            with patch("web_session_context.get_session_store", return_value=store):
                _seed_messages(store, sid, msgs)
                note = build_continue_context_note(sid, "能做成工作流吗")
                self.assertIn("近期上下文摘要", note)
                self.assertIn("家族怪兽挑战", note)
                self.assertNotIn("切换新的 Cursor Agent", note)

    def test_continue_context_skipped_when_rotating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            store = WebSessionStore(
                index_path=data / "sessions.json",
                messages_dir=data / "messages",
            )
            meta = store.create_session(owner_id="u1", owner_label="User")
            sid = meta.id
            msgs = [
                ChatMessage(role="user", content="家族怪兽挑战玩法分析")
            ] * 85
            with patch("web_session_context.get_session_store", return_value=store):
                _seed_messages(store, sid, msgs)
                self.assertEqual(build_continue_context_note(sid, "能做成工作流吗"), "")

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
                _seed_messages(store, sid, msgs)
                self.assertTrue(session_looks_like_pk_atm(sid))
                hint = pk_atm_prompt_hint("有没有生成钉钉文档", session_id=sid)
                self.assertIsNotNone(hint)


if __name__ == "__main__":
    unittest.main()
