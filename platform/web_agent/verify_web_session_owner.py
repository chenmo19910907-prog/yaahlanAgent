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

from web_session_store import WebSessionStore, filter_sessions_by_scope, filter_sessions_by_search  # noqa: E402


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


class SortSessionsForDisplayTest(unittest.TestCase):
    def test_running_unpinned_after_pinned_before_idle(self) -> None:
        from web_session_store import sort_sessions_for_display

        sessions = [
            {"id": "idle_new", "pinned": False, "updated_at": "2026-08-05T12:00:00+00:00", "running": False},
            {"id": "run_old", "pinned": False, "updated_at": "2026-08-05T10:00:00+00:00", "running": True},
            {"id": "pin", "pinned": True, "pinned_at": "2026-08-05T08:00:00+00:00", "updated_at": "2026-08-05T09:00:00+00:00", "running": True},
            {"id": "run_new", "pinned": False, "updated_at": "2026-08-05T11:00:00+00:00", "running": True},
        ]
        ordered = [s["id"] for s in sort_sessions_for_display(sessions)]
        self.assertEqual(ordered, ["pin", "run_new", "run_old", "idle_new"])


class WebSessionSearchTest(unittest.TestCase):
    def test_filter_sessions_by_search_matches_question_answer_and_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "sessions.json"
            messages_dir = root / "messages"
            messages_dir.mkdir()
            sid = "searchsess000001"
            index.write_text(
                json.dumps(
                    {
                        sid: {
                            "title": "4707充值90万钻石",
                            "created_at": "2026-08-03T08:00:00+00:00",
                            "updated_at": "2026-08-03T09:00:00+00:00",
                            "message_count": 3,
                            "source": "web",
                            "web_owner_id": "alice",
                            "web_owner_label": "Alice",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (messages_dir / f"{sid}.json").write_text(
                json.dumps(
                    [
                        {
                            "role": "user",
                            "content": "4707充值90万钻石",
                            "timestamp": "2026-08-03T08:00:00+00:00",
                        },
                        {
                            "role": "assistant",
                            "content": "provideDiamond 返回 redis client error",
                            "timestamp": "2026-08-03T09:00:00+00:00",
                        },
                        {
                            "role": "user",
                            "content": "再试一次",
                            "timestamp": "2026-08-03T09:01:00+00:00",
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = WebSessionStore(index_path=index, messages_dir=messages_dir)
            items = store.list_sessions(enrich_names=False)
            by_title = filter_sessions_by_search(
                items,
                "充值",
                load_messages=store.get_messages,
            )
            self.assertEqual(len(by_title), 1)
            self.assertIn("充值", by_title[0][1])
            by_answer = filter_sessions_by_search(
                items,
                "provideDiamond",
                load_messages=store.get_messages,
            )
            self.assertEqual(len(by_answer), 1)
            self.assertTrue(by_answer[0][1].startswith("答 ·"))
            by_owner = filter_sessions_by_search(
                items,
                "alice",
                load_messages=store.get_messages,
                known_labels={"alice": "Alice"},
            )
            self.assertEqual(len(by_owner), 1)
            empty = filter_sessions_by_search(
                items,
                "不存在的关键词xyz",
                load_messages=store.get_messages,
            )
            self.assertEqual(empty, [])


class WebSessionScopeFilterTest(unittest.TestCase):
    def test_filter_sessions_by_scope_mine_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "sessions.json"
            messages_dir = root / "messages"
            messages_dir.mkdir()
            index.write_text(
                json.dumps(
                    {
                        "mine000000000001": {
                            "title": "我的会话",
                            "created_at": "2026-08-03T08:00:00+00:00",
                            "updated_at": "2026-08-03T09:00:00+00:00",
                            "message_count": 1,
                            "source": "web",
                            "web_owner_id": "alice",
                            "web_owner_label": "Alice",
                        },
                        "other00000000001": {
                            "title": "他人会话",
                            "created_at": "2026-08-03T08:00:00+00:00",
                            "updated_at": "2026-08-03T09:00:00+00:00",
                            "message_count": 1,
                            "source": "web",
                            "web_owner_id": "bob",
                            "web_owner_label": "Bob",
                        },
                        "ding000000000001": {
                            "title": "钉钉会话",
                            "created_at": "2026-08-03T08:00:00+00:00",
                            "updated_at": "2026-08-03T09:00:00+00:00",
                            "message_count": 1,
                            "source": "dingtalk",
                            "dingtalk_owner_id": "alice",
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = WebSessionStore(index_path=index, messages_dir=messages_dir)
            items = store.list_sessions(enrich_names=False)
            all_items = filter_sessions_by_scope(items, "all", viewer_staff_id="alice")
            mine_items = filter_sessions_by_scope(items, "mine", viewer_staff_id="alice")
            self.assertEqual(len(all_items), 3)
            self.assertEqual(
                {item.id for item in mine_items},
                {"mine000000000001", "ding000000000001"},
            )
            self.assertEqual(filter_sessions_by_scope(items, "mine", viewer_staff_id=""), [])


class WebSessionCustomTitleTest(unittest.TestCase):
    def test_custom_title_overrides_display_and_clears_to_auto(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "sessions.json"
            messages_dir = root / "messages"
            messages_dir.mkdir()
            sid = "customtitle00001"
            index.write_text(
                json.dumps(
                    {
                        sid: {
                            "title": "自动标题来自首问",
                            "created_at": "2026-08-03T08:00:00+00:00",
                            "updated_at": "2026-08-03T09:00:00+00:00",
                            "message_count": 1,
                            "source": "web",
                            "web_owner_id": "alice",
                            "web_owner_label": "Alice",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (messages_dir / f"{sid}.json").write_text(
                json.dumps(
                    [{"role": "user", "content": "自动标题来自首问", "timestamp": "2026-08-03T09:00:00+00:00"}],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = WebSessionStore(index_path=index, messages_dir=messages_dir)
            meta = store.get_session(sid)
            assert meta is not None
            self.assertEqual(meta.display_title(), "自动标题来自首问")

            ok, err = store.set_session_custom_title(sid, title="我的自定义标题")
            self.assertTrue(ok)
            self.assertEqual(err, "")
            meta = store.get_session(sid)
            assert meta is not None
            self.assertEqual(meta.custom_title, "我的自定义标题")
            self.assertEqual(meta.display_title(), "我的自定义标题")
            payload = meta.to_dict()
            self.assertEqual(payload["title"], "我的自定义标题")
            self.assertEqual(payload["auto_title"], "自动标题来自首问")

            ok, err = store.set_session_custom_title(sid, title="")
            self.assertTrue(ok)
            meta = store.get_session(sid)
            assert meta is not None
            self.assertEqual(meta.custom_title, "")
            self.assertEqual(meta.display_title(), "自动标题来自首问")

    def test_custom_title_not_lost_when_stale_store_saves_after_rename(self) -> None:
        """模拟 Web 服务与 worker 多进程：worker 内存过期时不应覆盖 custom_title。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "sessions.json"
            messages_dir = root / "messages"
            messages_dir.mkdir()
            sid = "staletitle000001"
            index.write_text(
                json.dumps(
                    {
                        sid: {
                            "title": "自动标题",
                            "created_at": "2026-08-03T08:00:00+00:00",
                            "updated_at": "2026-08-03T09:00:00+00:00",
                            "message_count": 1,
                            "source": "web",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (messages_dir / f"{sid}.json").write_text(
                json.dumps(
                    [{"role": "user", "content": "自动标题", "timestamp": "2026-08-03T09:00:00+00:00"}],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            stale_store = WebSessionStore(index_path=index, messages_dir=messages_dir)
            other_store = WebSessionStore(index_path=index, messages_dir=messages_dir)
            ok, err = other_store.set_session_custom_title(sid, title="PK提款机协作案例")
            self.assertTrue(ok)
            self.assertEqual(err, "")

            # 模拟 worker 在 reload 后、落盘前另一进程写入 custom_title 的竞态
            from contextlib import contextmanager

            @contextmanager
            def _skip_exclusive_reload():
                with stale_store._lock:
                    yield

            stale_store._exclusive_index = _skip_exclusive_reload  # type: ignore[method-assign]
            stale_store.append_message(sid, "assistant", "回复内容")

            fresh_store = WebSessionStore(index_path=index, messages_dir=messages_dir)
            meta = fresh_store.get_session(sid)
            assert meta is not None
            self.assertEqual(meta.custom_title, "PK提款机协作案例")
            self.assertEqual(meta.display_title(), "PK提款机协作案例")


    def test_legacy_title_promoted_to_custom_title(self) -> None:
        """旧版仅写入 title 的手动标题，应在刷新 meta 时迁移到 custom_title。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "sessions.json"
            messages_dir = root / "messages"
            messages_dir.mkdir()
            sid = "legacytitle00001"
            index.write_text(
                json.dumps(
                    {
                        sid: {
                            "title": "PK提款机协作案例",
                            "created_at": "2026-08-03T08:00:00+00:00",
                            "updated_at": "2026-08-03T09:00:00+00:00",
                            "message_count": 2,
                            "source": "web",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (messages_dir / f"{sid}.json").write_text(
                json.dumps(
                    [
                        {
                            "role": "user",
                            "content": "首条提问",
                            "timestamp": "2026-08-03T09:00:00+00:00",
                        },
                        {
                            "role": "user",
                            "content": "第二条提问内容",
                            "timestamp": "2026-08-03T10:00:00+00:00",
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = WebSessionStore(index_path=index, messages_dir=messages_dir)
            store.list_sessions()
            meta = store.get_session(sid)
            assert meta is not None
            self.assertEqual(meta.custom_title, "PK提款机协作案例")
            self.assertEqual(meta.title, "第二条提问内容")
            self.assertEqual(meta.display_title(), "PK提款机协作案例")

    def test_new_question_does_not_lock_old_auto_title_as_custom(self) -> None:
        """历史会话追加新提问时，不应把首问自动标题误判为 custom_title。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "sessions.json"
            messages_dir = root / "messages"
            messages_dir.mkdir()
            sid = "oldsession000001"
            first_q = "4707充值90万钻石"
            second_q = "取消置顶无效了"
            index.write_text(
                json.dumps(
                    {
                        sid: {
                            "title": first_q,
                            "created_at": "2026-08-03T08:00:00+00:00",
                            "updated_at": "2026-08-03T09:00:00+00:00",
                            "message_count": 2,
                            "source": "web",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (messages_dir / f"{sid}.json").write_text(
                json.dumps(
                    [
                        {
                            "role": "user",
                            "content": first_q,
                            "timestamp": "2026-08-03T09:00:00+00:00",
                        },
                        {
                            "role": "assistant",
                            "content": "首条回复",
                            "timestamp": "2026-08-03T09:01:00+00:00",
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = WebSessionStore(index_path=index, messages_dir=messages_dir)
            store.append_message(sid, "user", second_q)
            meta = store.get_session(sid)
            assert meta is not None
            self.assertEqual(meta.custom_title, "")
            self.assertEqual(meta.title, second_q)
            self.assertEqual(meta.display_title(), second_q)

    def test_mistaken_custom_title_cleared_on_next_refresh(self) -> None:
        """已误写入 custom_title 的旧自动标题，刷新 meta 后应自动清除。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "sessions.json"
            messages_dir = root / "messages"
            messages_dir.mkdir()
            sid = "mistaketitle0001"
            first_q = "4707充值90万钻石"
            second_q = "取消置顶无效了"
            index.write_text(
                json.dumps(
                    {
                        sid: {
                            "title": second_q,
                            "custom_title": first_q,
                            "created_at": "2026-08-03T08:00:00+00:00",
                            "updated_at": "2026-08-03T10:00:00+00:00",
                            "message_count": 3,
                            "source": "web",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (messages_dir / f"{sid}.json").write_text(
                json.dumps(
                    [
                        {
                            "role": "user",
                            "content": first_q,
                            "timestamp": "2026-08-03T09:00:00+00:00",
                        },
                        {
                            "role": "assistant",
                            "content": "首条回复",
                            "timestamp": "2026-08-03T09:01:00+00:00",
                        },
                        {
                            "role": "user",
                            "content": second_q,
                            "timestamp": "2026-08-03T10:00:00+00:00",
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = WebSessionStore(index_path=index, messages_dir=messages_dir)
            store.list_sessions()
            meta = store.get_session(sid)
            assert meta is not None
            self.assertEqual(meta.custom_title, "")
            self.assertEqual(meta.display_title(), second_q)


class WebSessionOwnerDisplayTest(unittest.TestCase):
    def test_dingtalk_owner_display_prefers_multi_source_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "sessions.json"
            messages_dir = root / "messages"
            messages_dir.mkdir()
            sid = "dingtalkowner001"
            index.write_text(
                json.dumps(
                    {
                        sid: {
                            "title": "钉钉 · Kaibo",
                            "created_at": "2026-08-03T08:00:00+00:00",
                            "updated_at": "2026-08-03T09:00:00+00:00",
                            "message_count": 1,
                            "source": "dingtalk",
                            "dingtalk_key": "cid:user:uid_kaibo",
                            "dingtalk_label": "Kaibo",
                            "dingtalk_owner_id": "uid_kaibo",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = WebSessionStore(index_path=index, messages_dir=messages_dir)
            meta = store.get_session(sid)
            assert meta is not None
            payload = meta.to_dict(known_labels={"uid_kaibo": "王凯波"})
            self.assertEqual(payload["dingtalk_owner"], "王凯波")
            self.assertEqual(payload["dingtalk_label"], "王凯波")


if __name__ == "__main__":
    unittest.main()
