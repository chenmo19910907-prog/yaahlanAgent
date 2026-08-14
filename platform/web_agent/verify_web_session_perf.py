#!/usr/bin/env python3
"""Web 会话存储性能相关回归测试。"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path

from web_session_store import (
    ChatMessage,
    SessionMeta,
    WebSessionStore,
    _now_iso,
    compute_messages_page_etag,
    compute_sessions_list_etag,
    estimate_messages_page_meta,
    filter_sessions_by_search,
)


class WebSessionPerfTest(unittest.TestCase):
    def _make_store_with_sessions(self, count: int) -> tuple[WebSessionStore, Path, Path, list[str]]:
        root = Path(tempfile.mkdtemp())
        index = root / "sessions.json"
        messages_dir = root / "messages"
        messages_dir.mkdir()
        session_ids: list[str] = []
        index_payload: dict[str, object] = {}
        for i in range(count):
            sid = f"sess{i:04d}"
            session_ids.append(sid)
            ts = f"2026-08-03T10:{i:02d}:00+00:00"
            (messages_dir / f"{sid}.json").write_text(
                json.dumps(
                    [
                        {"role": "user", "content": f"question {i}", "timestamp": ts},
                        {"role": "assistant", "content": f"answer {i}", "timestamp": ts},
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            file_mtime = (messages_dir / f"{sid}.json").stat().st_mtime
            index_payload[sid] = {
                "title": f"question {i}",
                "created_at": ts,
                "updated_at": ts,
                "message_count": 2,
                "source": "web",
                "latest_preview": f"answer {i}",
                "messages_mtime": file_mtime,
            }
        index.write_text(json.dumps(index_payload, ensure_ascii=False), encoding="utf-8")
        store = WebSessionStore(index_path=index, messages_dir=messages_dir)
        return store, index, messages_dir, session_ids

    def test_list_sessions_skips_message_reload_when_mtime_synced(self) -> None:
        store, _, _, _ = self._make_store_with_sessions(40)
        original_load = store._load_messages
        load_calls = 0

        def counting_load(session_id: str) -> list[ChatMessage]:
            nonlocal load_calls
            load_calls += 1
            return original_load(session_id)

        store._load_messages = counting_load  # type: ignore[method-assign]
        t0 = time.perf_counter()
        items = store.list_sessions(enrich_names=False)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        self.assertEqual(len(items), 40)
        self.assertEqual(load_calls, 0)
        self.assertLess(elapsed_ms, 120.0)

    def test_get_messages_tail_and_before(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "sessions.json"
            messages_dir = root / "messages"
            messages_dir.mkdir()
            sid = "paginate000001"
            rows = []
            for i in range(10):
                rows.append(
                    {
                        "role": "user" if i % 2 == 0 else "assistant",
                        "content": f"msg-{i}",
                        "timestamp": f"2026-08-03T10:{i:02d}:00+00:00",
                    }
                )
            (messages_dir / f"{sid}.json").write_text(
                json.dumps(rows, ensure_ascii=False),
                encoding="utf-8",
            )
            index.write_text(
                json.dumps(
                    {
                        sid: {
                            "title": "分页测试",
                            "created_at": _now_iso(),
                            "updated_at": _now_iso(),
                            "message_count": 10,
                            "source": "web",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = WebSessionStore(index_path=index, messages_dir=messages_dir)
            tail_msgs, tail_meta = store.get_messages(sid, tail=4)
            self.assertEqual(len(tail_msgs), 4)
            self.assertEqual(tail_msgs[0].content, "msg-6")
            self.assertTrue(tail_meta["has_older"])
            self.assertEqual(tail_meta["total"], 10)

            before_ts = tail_msgs[0].timestamp
            older_msgs, older_meta = store.get_messages(sid, before=before_ts, limit=3)
            self.assertEqual(len(older_msgs), 3)
            self.assertEqual(older_msgs[-1].content, "msg-5")
            self.assertTrue(older_meta["has_older"])


    def test_search_skips_message_load_when_title_matches(self) -> None:
        meta = SessionMeta(
            id="search001",
            title="性能优化专项",
            created_at=_now_iso(),
            updated_at=_now_iso(),
            message_count=99,
            latest_preview="最后一条预览",
        )
        load_calls = 0

        def counting_load(session_id: str) -> list[ChatMessage]:
            nonlocal load_calls
            load_calls += 1
            return [ChatMessage(role="user", content="hidden keyword only in body")]

        hits = filter_sessions_by_search(
            [meta],
            "性能优化",
            load_messages=counting_load,
        )
        self.assertEqual(len(hits), 1)
        self.assertEqual(load_calls, 0)

    def test_tail_reads_sidecar_without_full_message_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "sessions.json"
            messages_dir = root / "messages"
            messages_dir.mkdir()
            sid = "tailsidecar01"
            rows = []
            for i in range(140):
                rows.append(
                    {
                        "role": "user" if i % 2 == 0 else "assistant",
                        "content": f"payload-{i}-" + ("x" * 900),
                        "timestamp": f"2026-08-03T10:{i % 60:02d}:00+00:00",
                    }
                )
            store = WebSessionStore(index_path=index, messages_dir=messages_dir)
            store._save_messages(sid, [  # type: ignore[attr-defined]
                ChatMessage(role=row["role"], content=row["content"], timestamp=row["timestamp"])
                for row in rows
            ])
            index.write_text(
                json.dumps(
                    {
                        sid: {
                            "title": "tail sidecar",
                            "created_at": _now_iso(),
                            "updated_at": _now_iso(),
                            "message_count": len(rows),
                            "source": "web",
                            "messages_mtime": store._messages_file_mtime(sid),  # type: ignore[attr-defined]
                            "has_assistant": True,
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = WebSessionStore(index_path=index, messages_dir=messages_dir)
            original_load = store._load_messages
            load_calls = 0

            def counting_load(session_id: str) -> list[ChatMessage]:
                nonlocal load_calls
                load_calls += 1
                return original_load(session_id)

            store._load_messages = counting_load  # type: ignore[method-assign]
            tail_msgs, tail_meta = store.get_messages(sid, tail=80)
            self.assertEqual(len(tail_msgs), 80)
            self.assertEqual(tail_msgs[-1].content, rows[-1]["content"])
            self.assertTrue(tail_meta["has_older"])
            self.assertEqual(load_calls, 0)

    def test_compute_sessions_list_etag_changes_with_running_flag(self) -> None:
        base = {
            "id": "sess001",
            "title": "demo",
            "updated_at": "2026-08-13T10:00:00+00:00",
            "message_count": 3,
            "messages_mtime": 123.0,
            "pinned": False,
            "latest_preview": "preview",
        }
        idle_tag = compute_sessions_list_etag([{**base, "running": False}])
        running_tag = compute_sessions_list_etag([{**base, "running": True}])
        self.assertNotEqual(idle_tag, running_tag)

    def test_list_sessions_lite_skips_derived_meta_sync(self) -> None:
        store, _, messages_dir, _ = self._make_store_with_sessions(40)
        stat_calls = 0
        original_stat = Path.stat

        def counting_stat(self, *args, **kwargs):
            nonlocal stat_calls
            if (
                self.parent == messages_dir
                and self.suffix == ".json"
                and not self.name.endswith(".json.tail")
            ):
                stat_calls += 1
            return original_stat(self, *args, **kwargs)

        Path.stat = counting_stat  # type: ignore[method-assign]
        try:
            store.list_sessions(enrich_names=False, sync_derived_meta=False)
        finally:
            Path.stat = original_stat  # type: ignore[method-assign]
        self.assertEqual(stat_calls, 0)

    def test_list_sessions_readonly_skips_exclusive_lock(self) -> None:
        store, _, _, _ = self._make_store_with_sessions(10)

        @contextmanager
        def forbidden_exclusive():
            raise AssertionError("readonly list must not acquire exclusive index lock")

        store._exclusive_index = forbidden_exclusive  # type: ignore[method-assign]
        items = store.list_sessions(readonly=True)
        self.assertEqual(len(items), 10)

    def test_compute_active_run_etag_changes_with_markdown(self) -> None:
        from web_run_store import compute_active_run_etag

        base = {
            "active": True,
            "run_id": "run001",
            "ack_line": "收到",
            "elapsed_line": "1s",
            "batch_line": "",
            "external_line": "",
            "phase_line": "思考中",
            "markdown": "hello",
            "process": None,
        }
        tag_a = compute_active_run_etag("sess001", base)
        tag_b = compute_active_run_etag(
            "sess001",
            {**base, "markdown": "hello world"},
        )
        self.assertNotEqual(tag_a, tag_b)
        inactive = compute_active_run_etag("sess001", {"active": False})
        self.assertNotEqual(tag_a, inactive)

    def test_compute_messages_page_etag_changes_with_tail(self) -> None:
        base_msg = {"role": "user", "content": "hello", "timestamp": "2026-08-13T10:00:00+00:00"}
        tail80 = compute_messages_page_etag(
            "sess001",
            messages_mtime=100.0,
            message_count=120,
            tail=80,
            total=120,
            has_older=True,
            offset=40,
        )
        tail40 = compute_messages_page_etag(
            "sess001",
            messages_mtime=100.0,
            message_count=120,
            tail=40,
            total=120,
            has_older=True,
            offset=80,
        )
        self.assertNotEqual(tail80, tail40)

    def test_messages_meta_etag_skips_message_body(self) -> None:
        page_meta = estimate_messages_page_meta(50, tail=80)
        self.assertIsNotNone(page_meta)
        meta_tag = compute_messages_page_etag(
            "sess001",
            messages_mtime=100.0,
            message_count=50,
            tail=80,
            total=int(page_meta["total"]),  # type: ignore[index]
            has_older=bool(page_meta["has_older"]),  # type: ignore[index]
            offset=int(page_meta["offset"]),  # type: ignore[index]
        )
        self.assertTrue(meta_tag.startswith('W/"'))

    def test_estimate_messages_page_meta_returns_none_for_before(self) -> None:
        self.assertIsNone(estimate_messages_page_meta(50, before="2026-08-13T10:00:00+00:00", limit=80))


if __name__ == "__main__":
    unittest.main()
