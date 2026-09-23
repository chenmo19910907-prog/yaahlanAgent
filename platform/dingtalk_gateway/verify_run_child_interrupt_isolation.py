#!/usr/bin/env python3
"""中断清理：仅终止目标 session 登记的进程，不误杀其它会话。"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(GATEWAY_DIR))

from run_child_processes import (  # noqa: E402
    is_pid_alive,
    kill_run_child_processes,
    list_run_child_pids,
    register_run_child,
)


class RunChildInterruptIsolationTests(unittest.TestCase):
    def test_kill_only_target_session_children(self) -> None:
        user_a = "web:interrupt-isolation-a"
        user_b = "web:interrupt-isolation-b"
        proc_a = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)"],
            start_new_session=True,
        )
        proc_b = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)"],
            start_new_session=True,
        )
        try:
            register_run_child(user_a, proc_a.pid)
            register_run_child(user_b, proc_b.pid)
            self.assertIn(proc_a.pid, list_run_child_pids(user_a))
            self.assertIn(proc_b.pid, list_run_child_pids(user_b))

            killed = kill_run_child_processes(user_a)
            self.assertEqual(killed, 1)

            proc_a.wait(timeout=5)
            self.assertIsNotNone(proc_a.poll())
            self.assertTrue(is_pid_alive(proc_b.pid))
            self.assertIn(proc_b.pid, list_run_child_pids(user_b))
        finally:
            kill_run_child_processes(user_b)
            if proc_b.poll() is None:
                proc_b.kill()
                proc_b.wait(timeout=3)
            if proc_a.poll() is None:
                proc_a.kill()
                proc_a.wait(timeout=3)

    def test_extra_root_pids_scoped_to_single_kill_call(self) -> None:
        user_a = "web:interrupt-extra-a"
        user_b = "web:interrupt-extra-b"
        worker_a = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)"],
            start_new_session=True,
        )
        worker_b = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)"],
            start_new_session=True,
        )
        try:
            killed = kill_run_child_processes(user_a, extra_root_pids=[worker_a.pid])
            self.assertEqual(killed, 1)
            worker_a.wait(timeout=5)
            self.assertIsNotNone(worker_a.poll())
            self.assertTrue(is_pid_alive(worker_b.pid))
            self.assertEqual(list_run_child_pids(user_a), [])
        finally:
            kill_run_child_processes(user_b, extra_root_pids=[worker_b.pid])
            if worker_b.poll() is None:
                worker_b.kill()
                worker_b.wait(timeout=3)
            if worker_a.poll() is None:
                worker_a.kill()
                worker_a.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
