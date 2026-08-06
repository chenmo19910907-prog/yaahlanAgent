#!/usr/bin/env python3
"""web_run_executor 单测。"""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(WEB_AGENT_DIR))

from web_run_executor import _start_run_in_thread, is_run_thread_alive, start_run_in_background  # noqa: E402
from web_run_store import RUN_STATUS_RUNNING, RunMeta, WebRunStore  # noqa: E402


class WebRunExecutorTests(unittest.TestCase):
    def test_is_run_thread_alive_tracks_background_run(self) -> None:
        started = threading.Event()
        release = threading.Event()

        def slow_run() -> None:
            started.set()
            release.wait(timeout=5.0)

        thread = threading.Thread(target=slow_run, daemon=True)
        rid = "test-run-alive"
        import web_run_executor as ex

        with ex._RUN_LOCK:
            ex._RUN_THREADS[rid] = thread
        thread.start()
        self.assertTrue(started.wait(timeout=2.0))
        self.assertTrue(is_run_thread_alive(rid))
        release.set()
        thread.join(timeout=2.0)
        with ex._RUN_LOCK:
            ex._RUN_THREADS.pop(rid, None)
        self.assertFalse(is_run_thread_alive(rid))

    def test_start_run_in_background_skips_duplicate(self) -> None:
        import tempfile

        import web_run_executor as ex

        with tempfile.TemporaryDirectory() as tmp:
            store = WebRunStore(root=Path(tmp) / "runs")
            rid = "dup123"
            store.create_run(
                RunMeta(
                    run_id=rid,
                    session_id="sess1",
                    message="hi",
                    display_message="hi",
                    model="composer",
                    enabled_external_agents=[],
                    author_id="u1",
                    author_label="U",
                    image_paths=[],
                    file_paths=[],
                    attachment_names=[],
                    worker_pid=0,
                    status=RUN_STATUS_RUNNING,
                    started_at=1.0,
                )
            )
            blocker = threading.Event()

            def stub_execute(run_id: str) -> int:
                blocker.wait(timeout=3.0)
                return 0

            original = ex.execute_web_run
            ex.execute_web_run = stub_execute  # type: ignore[method-assign]
            try:
                pid1 = _start_run_in_thread(rid)
                time.sleep(0.05)
                pid2 = _start_run_in_thread(rid)
                self.assertEqual(pid1, pid2)
                self.assertTrue(is_run_thread_alive(rid))
            finally:
                blocker.set()
                if is_run_thread_alive(rid):
                    with ex._RUN_LOCK:
                        t = ex._RUN_THREADS.get(rid)
                    if t is not None:
                        t.join(timeout=2.0)
                ex.execute_web_run = original  # type: ignore[method-assign]
                with ex._RUN_LOCK:
                    ex._RUN_THREADS.pop(rid, None)


if __name__ == "__main__":
    unittest.main()
