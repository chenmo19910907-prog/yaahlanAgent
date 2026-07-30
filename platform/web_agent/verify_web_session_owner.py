#!/usr/bin/env python3
"""web_session_store 会话归属锁定与只读单测。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_AGENT_DIR))

from web_session_store import WebSessionStore  # noqa: E402


class WebSessionOwnerLockTest(unittest.TestCase):
    def test_ensure_web_owner_locks_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "sessions.json"
            messages_dir = root / "messages"
            messages_dir.mkdir()
            sid = "abc123lock0001"
            index.write_text(
                json.dumps(
                    {
                        sid: {
                            "title": "测试",
                            "created_at": "2026-07-24T08:00:00+00:00",
                            "updated_at": "2026-07-24T08:00:00+00:00",
                            "message_count": 0,
                            "source": "web",
                            "dingtalk_key": "",
                            "dingtalk_label": "",
                            "dingtalk_owner_id": "",
                            "web_owner_id": "",
                            "web_owner_label": "",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = WebSessionStore(index_path=index, messages_dir=messages_dir)
            self.assertTrue(
                store.ensure_web_owner(
                    sid,
                    owner_id="owner_a",
                    owner_label="用户A",
                )
            )
            self.assertFalse(
                store.ensure_web_owner(
                    sid,
                    owner_id="owner_b",
                    owner_label="用户B",
                )
            )
            meta = store.get_session(sid)
            assert meta is not None
            self.assertEqual(meta.web_owner_id, "owner_a")
            self.assertEqual(meta.web_owner_label, "用户A")

    def test_read_only_for_non_owner_web_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "sessions.json"
            messages_dir = root / "messages"
            messages_dir.mkdir()
            sid = "abc123readonly"
            index.write_text(
                json.dumps(
                    {
                        sid: {
                            "title": "他人会话",
                            "created_at": "2026-07-24T08:00:00+00:00",
                            "updated_at": "2026-07-24T08:00:00+00:00",
                            "message_count": 2,
                            "source": "web",
                            "dingtalk_key": "",
                            "dingtalk_label": "",
                            "dingtalk_owner_id": "",
                            "web_owner_id": "owner_a",
                            "web_owner_label": "用户A",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = WebSessionStore(index_path=index, messages_dir=messages_dir)
            meta = store.get_session(sid)
            assert meta is not None
            self.assertTrue(meta.is_read_only_for_viewer("owner_b"))
            self.assertFalse(meta.is_read_only_for_viewer("owner_a"))
            payload = meta.to_dict(viewer_staff_id="owner_b")
            self.assertTrue(payload.get("read_only"))

    def test_collaborator_can_write_web_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "sessions.json"
            messages_dir = root / "messages"
            messages_dir.mkdir()
            sid = "abc123collab01"
            index.write_text(
                json.dumps(
                    {
                        sid: {
                            "title": "共同对话",
                            "created_at": "2026-07-24T08:00:00+00:00",
                            "updated_at": "2026-07-24T08:00:00+00:00",
                            "message_count": 0,
                            "source": "web",
                            "dingtalk_key": "",
                            "dingtalk_label": "",
                            "dingtalk_owner_id": "",
                            "web_owner_id": "owner_a",
                            "web_owner_label": "用户A",
                            "web_collaborator_ids": ["user_b"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = WebSessionStore(index_path=index, messages_dir=messages_dir)
            meta = store.get_session(sid)
            assert meta is not None
            self.assertFalse(meta.is_read_only_for_viewer("user_b"))
            payload = meta.to_dict(viewer_staff_id="user_b")
            self.assertTrue(payload.get("is_collaborator"))
            self.assertNotIn("read_only", payload)

    def test_set_web_collaborators_owner_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "sessions.json"
            messages_dir = root / "messages"
            messages_dir.mkdir()
            sid = "abc123collab02"
            index.write_text(
                json.dumps(
                    {
                        sid: {
                            "title": "共同对话",
                            "created_at": "2026-07-24T08:00:00+00:00",
                            "updated_at": "2026-07-24T08:00:00+00:00",
                            "message_count": 0,
                            "source": "web",
                            "dingtalk_key": "",
                            "dingtalk_label": "",
                            "dingtalk_owner_id": "",
                            "web_owner_id": "owner_a",
                            "web_owner_label": "用户A",
                            "web_collaborator_ids": [],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = WebSessionStore(index_path=index, messages_dir=messages_dir)
            ok, err = store.set_web_collaborators(
                sid,
                owner_id="owner_b",
                collaborator_ids=["user_c"],
            )
            self.assertFalse(ok)
            self.assertEqual(err, "forbidden")
            ok, err = store.set_web_collaborators(
                sid,
                owner_id="owner_a",
                collaborator_ids=["user_c", "owner_a", "user_c"],
            )
            self.assertTrue(ok)
            self.assertEqual(err, "")
            meta = store.get_session(sid)
            assert meta is not None
            self.assertEqual(meta.web_collaborator_ids, ["user_c"])

    def test_pin_session_sort_and_unpin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "sessions.json"
            messages_dir = root / "messages"
            messages_dir.mkdir()
            sid_a = "abc123pina0001"
            sid_b = "abc123pinb0002"
            sid_c = "abc123pinc0003"
            index.write_text(
                json.dumps(
                    {
                        sid_a: {
                            "title": "A",
                            "created_at": "2026-07-24T08:00:00+00:00",
                            "updated_at": "2026-07-30T08:00:00+00:00",
                            "message_count": 1,
                            "source": "web",
                            "dingtalk_key": "",
                            "dingtalk_label": "",
                            "dingtalk_owner_id": "",
                            "web_owner_id": "owner_a",
                            "web_owner_label": "用户A",
                            "pinned_at": "2026-07-30T06:00:00+00:00",
                        },
                        sid_b: {
                            "title": "B",
                            "created_at": "2026-07-24T08:00:00+00:00",
                            "updated_at": "2026-07-30T09:00:00+00:00",
                            "message_count": 1,
                            "source": "web",
                            "dingtalk_key": "",
                            "dingtalk_label": "",
                            "dingtalk_owner_id": "",
                            "web_owner_id": "owner_b",
                            "web_owner_label": "用户B",
                            "pinned_at": "2026-07-30T07:00:00+00:00",
                        },
                        sid_c: {
                            "title": "C",
                            "created_at": "2026-07-24T08:00:00+00:00",
                            "updated_at": "2026-07-30T10:00:00+00:00",
                            "message_count": 1,
                            "source": "web",
                            "dingtalk_key": "",
                            "dingtalk_label": "",
                            "dingtalk_owner_id": "",
                            "web_owner_id": "owner_c",
                            "web_owner_label": "用户C",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = WebSessionStore(index_path=index, messages_dir=messages_dir)
            ordered = [item.id for item in store.list_sessions(enrich_names=False)]
            self.assertEqual(ordered, [sid_a, sid_b, sid_c])

            ok, err = store.set_session_pinned(sid_a, pinned=False)
            self.assertTrue(ok)
            self.assertEqual(err, "")
            ordered = [item.id for item in store.list_sessions(enrich_names=False)]
            self.assertEqual(ordered, [sid_b, sid_c, sid_a])

            ok, err = store.set_session_pinned(sid_c, pinned=True)
            self.assertTrue(ok)
            ordered = [item.id for item in store.list_sessions(enrich_names=False)]
            self.assertEqual(ordered[:2], [sid_b, sid_c])
            self.assertEqual(ordered[2], sid_a)


if __name__ == "__main__":
    unittest.main()
