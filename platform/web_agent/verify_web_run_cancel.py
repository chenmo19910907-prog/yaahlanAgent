#!/usr/bin/env python3
"""Web Agent 中断思考：不误杀 daemon。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(WEB_AGENT_DIR))

from web_run_executor import is_shared_worker_daemon_pid  # noqa: E402


class SharedWorkerDaemonTests(unittest.TestCase):
    def test_tracked_daemon_pid_is_shared(self) -> None:
        with mock.patch("web_run_executor.worker_daemon_pid", return_value=4242):
            self.assertTrue(is_shared_worker_daemon_pid(4242))

    def test_one_shot_worker_pid_not_shared_when_daemon_tracked(self) -> None:
        with mock.patch("web_run_executor.worker_daemon_pid", return_value=4242):
            with mock.patch("web_run_executor.subprocess.run") as run_mock:
                run_mock.return_value.returncode = 1
                self.assertFalse(is_shared_worker_daemon_pid(9999))

    def test_pgrep_fallback_detects_daemon(self) -> None:
        with mock.patch("web_run_executor.worker_daemon_pid", return_value=0):
            with mock.patch("web_run_executor.subprocess.run") as run_mock:
                run_mock.return_value.returncode = 0
                run_mock.return_value.stdout = "7777\n"
                self.assertTrue(is_shared_worker_daemon_pid(7777))


if __name__ == "__main__":
    unittest.main()
