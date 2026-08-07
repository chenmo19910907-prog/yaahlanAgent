#!/usr/bin/env python3
"""验证：服务重启后恢复 RUNNING 任务时会挂上 event tailer（SSE 可续流）。"""

from __future__ import annotations

import sys
import tempfile
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


if __name__ == "__main__":
    unittest.main()
