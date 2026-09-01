#!/usr/bin/env python3
"""Web Agent 中断：仅终止目标 run，不误杀其它会话 worker。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(WEB_AGENT_DIR))

from verify_import_stubs import stub_cursor_runner  # noqa: E402

stub_cursor_runner()

import server  # noqa: E402
from server import ActiveRun, _interrupt_active_run  # noqa: E402
from web_run_store import RUN_STATUS_RUNNING, RunMeta, WebRunStore  # noqa: E402


class InterruptIsolationTests(unittest.TestCase):
    def test_interrupt_does_not_request_cancel_on_http_task_session(self) -> None:
        """request_cancel 会清空 HTTP 进程全部子进程，须避免。"""
        run = ActiveRun(run_id="run_a", session_id="sess_a")
        run.task_session.begin("hello", conversation_id="web:sess_a")

        meta = RunMeta(
            run_id="run_a",
            session_id="sess_a",
            message="hello",
            display_message="hello",
            model="composer",
            enabled_external_agents=[],
            author_id="u1",
            author_label="U",
            image_paths=[],
            file_paths=[],
            attachment_names=[],
            worker_pid=4242,
            status=RUN_STATUS_RUNNING,
            started_at=1.0,
        )
        store = mock.Mock()
        store.get_run.return_value = meta

        session_store = mock.Mock()
        session_store.user_key.return_value = "web:sess_a"

        with mock.patch("server.get_run_store", return_value=store):
            with mock.patch("server.get_session_store", return_value=session_store):
                with mock.patch("server._notify_run_interrupted", return_value=True):
                    with mock.patch(
                        "run_child_processes.kill_run_child_processes",
                        return_value=0,
                    ) as kill_children:
                        with mock.patch(
                            "web_run_executor._terminate_worker_process",
                        ) as terminate_worker:
                            with mock.patch(
                                "web_run_executor.is_shared_worker_daemon_pid",
                                return_value=False,
                            ):
                                with mock.patch(
                                    "user_agent_pool.get_user_agent_pool",
                                ) as pool_factory:
                                    pool = mock.Mock()
                                    pool_factory.return_value = pool
                                    with mock.patch.object(
                                        run.task_session,
                                        "request_cancel",
                                    ) as request_cancel:
                                        self.assertTrue(_interrupt_active_run(run))

        request_cancel.assert_not_called()
        store.request_cancel.assert_called_once_with("run_a")
        kill_children.assert_called_once_with("web:sess_a")
        terminate_worker.assert_called_once_with(4242)
        pool.invalidate.assert_called_once_with("web:sess_a")


if __name__ == "__main__":
    unittest.main()
