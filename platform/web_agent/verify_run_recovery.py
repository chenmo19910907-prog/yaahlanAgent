#!/usr/bin/env python3
"""验证：服务重启后恢复 RUNNING 任务时会挂上 event tailer（SSE 可续流）。"""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(WEB_AGENT_DIR))

from web_run_store import RUN_STATUS_RUNNING, RunMeta, WebRunStore  # noqa: E402


class RunRecoveryTailerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = WebRunStore(root=Path(self._tmpdir.name) / "runs")
        self.meta = RunMeta(
            run_id="rec001",
            session_id="sess001",
            message="hello",
            display_message="hello",
            model="composer-2.5",
            enabled_external_agents=[],
            author_id="",
            author_label="",
            image_paths=[],
            file_paths=[],
            attachment_names=[],
            worker_pid=4242,
            status=RUN_STATUS_RUNNING,
            started_at=1_700_000_000.0,
        )
        self.store.create_run(self.meta)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_recover_running_meta_attaches_tailers_when_worker_alive(self) -> None:
        import server as srv

        srv.RUN_MANAGER._runs.clear()
        with mock.patch.object(srv, "get_run_store", return_value=self.store):
            with mock.patch.object(self.store, "is_worker_alive", return_value=True):
                with mock.patch.object(srv, "_attach_run_tailers") as attach_mock:
                    run = srv._recover_running_meta(self.meta)
        self.assertEqual(run.run_id, "rec001")
        attach_mock.assert_called_once()
        self.assertIs(attach_mock.call_args[0][0], run)
        self.assertIs(attach_mock.call_args[0][1], self.meta)

    def test_recover_running_meta_reuses_existing_run_without_duplicate_tailers(self) -> None:
        import server as srv

        srv.RUN_MANAGER._runs.clear()
        existing = srv.RUN_MANAGER.create("sess001", run_id="rec001")
        existing.tailers_attached = True
        with mock.patch.object(srv, "get_run_store", return_value=self.store):
            with mock.patch.object(self.store, "is_worker_alive", return_value=True):
                with mock.patch.object(srv, "_attach_run_tailers") as attach_mock:
                    run = srv._recover_running_meta(self.meta)
        self.assertIs(run, existing)
        attach_mock.assert_not_called()

    def test_active_run_from_store_meta_restores_started_at_from_meta(self) -> None:
        import server as srv

        srv.RUN_MANAGER._runs.clear()
        wall_started = time.time() - 42
        old_meta = RunMeta(
            run_id="rec003",
            session_id="sess003",
            message="hello",
            display_message="hello",
            model="composer-2.5",
            enabled_external_agents=[],
            author_id="",
            author_label="",
            image_paths=[],
            file_paths=[],
            attachment_names=[],
            worker_pid=4242,
            status=RUN_STATUS_RUNNING,
            started_at=wall_started,
        )
        self.store.create_run(old_meta)
        with mock.patch.object(srv, "get_run_store", return_value=self.store):
            run = srv._active_run_from_store_meta(old_meta)
        self.assertGreaterEqual(time.monotonic() - run.started_at, 41.0)

    def test_recover_running_meta_respawns_recent_dead_worker(self) -> None:
        import server as srv

        srv.RUN_MANAGER._runs.clear()
        recent = RunMeta(
            run_id="rec002",
            session_id="sess002",
            message="hello",
            display_message="hello",
            model="composer-2.5",
            enabled_external_agents=[],
            author_id="",
            author_label="",
            image_paths=[],
            file_paths=[],
            attachment_names=[],
            worker_pid=4242,
            status=RUN_STATUS_RUNNING,
            started_at=time.time() - 5,
        )
        self.store.create_run(recent)
        with mock.patch.object(srv, "get_run_store", return_value=self.store):
            with mock.patch.object(self.store, "is_worker_alive", side_effect=[False, True]):
                with mock.patch.object(srv, "_start_run_worker", return_value=99999) as spawn_mock:
                    with mock.patch.object(srv, "_attach_run_tailers") as attach_mock:
                        with mock.patch.object(srv, "_finalize_orphan_run") as finalize_mock:
                            run = srv._recover_running_meta(recent, allow_fresh_spawn=True)
        spawn_mock.assert_called_once_with("rec002")
        attach_mock.assert_called_once()
        finalize_mock.assert_not_called()
        self.assertEqual(run.run_id, "rec002")

    def test_get_or_recover_run_allows_fresh_spawn(self) -> None:
        import server as srv

        srv.RUN_MANAGER._runs.clear()
        recent = RunMeta(
            run_id="rec004",
            session_id="sess004",
            message="hello",
            display_message="hello",
            model="composer-2.5",
            enabled_external_agents=[],
            author_id="",
            author_label="",
            image_paths=[],
            file_paths=[],
            attachment_names=[],
            worker_pid=4242,
            status=RUN_STATUS_RUNNING,
            started_at=time.time() - 5,
        )
        self.store.create_run(recent)
        with mock.patch.object(srv, "get_run_store", return_value=self.store):
            with mock.patch.object(self.store, "is_worker_alive", side_effect=[False, True]):
                with mock.patch.object(srv, "_try_respawn_recent_run") as respawn_mock:
                    fake_run = srv.RUN_MANAGER.create("sess004", run_id="rec004")
                    respawn_mock.return_value = fake_run
                    run = srv._get_or_recover_run("rec004")
        respawn_mock.assert_called_once()
        self.assertIs(run, fake_run)

    def test_finalize_orphan_run_skips_when_worker_alive(self) -> None:
        import server as srv

        meta = RunMeta(
            run_id="rec005",
            session_id="sess005",
            message="hello",
            display_message="hello",
            model="composer-2.5",
            enabled_external_agents=[],
            author_id="",
            author_label="",
            image_paths=[],
            file_paths=[],
            attachment_names=[],
            worker_pid=4242,
            status=RUN_STATUS_RUNNING,
            started_at=time.time() - 5,
        )
        self.store.create_run(meta)
        with mock.patch.object(srv, "get_run_store", return_value=self.store):
            with mock.patch.object(self.store, "is_worker_alive", return_value=True):
                with mock.patch.object(srv, "get_session_store") as session_store_mock:
                    srv._finalize_orphan_run(meta)
        session_store_mock.assert_not_called()
        refreshed = self.store.get_run("rec005")
        assert refreshed is not None
        self.assertEqual(refreshed.status, RUN_STATUS_RUNNING)


if __name__ == "__main__":
    unittest.main()
