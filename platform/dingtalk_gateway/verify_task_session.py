#!/usr/bin/env python3
"""task_session 中断清理单测。"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

GATEWAY_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(GATEWAY_DIR))

from task_session import (  # noqa: E402
    TaskInterrupted,
    TaskSession,
    _kill_process_tree,
    _list_child_pids,
    _terminate_child_processes,
)


class TaskSessionCancelTests(unittest.TestCase):
    def test_check_cancelled_runs_cleanup_once(self) -> None:
        session = TaskSession()
        session.begin("demo", conversation_id="u1")
        session.arm_cancel()
        with mock.patch.object(session, "_apply_cancel_cleanup") as cleanup:
            with self.assertRaises(TaskInterrupted):
                session.check_cancelled()
            with self.assertRaises(TaskInterrupted):
                session.check_cancelled()
            self.assertEqual(cleanup.call_count, 2)

    def test_request_cancel_kills_registered_subprocess(self) -> None:
        session = TaskSession()
        session.begin("sleep", conversation_id="u1")
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        session.register_subprocess(proc)
        try:
            self.assertIsNone(proc.poll())
            self.assertTrue(session.request_cancel())
            proc.wait(timeout=3)
            self.assertIsNotNone(proc.poll())
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=3)

    def test_kill_process_tree_terminates_child(self) -> None:
        script = (
            "import subprocess, sys, time\n"
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            "time.sleep(60)\n"
        )
        parent = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 2.0
            children: list[int] = []
            while time.monotonic() < deadline:
                children = _list_child_pids(parent.pid)
                if children:
                    break
                time.sleep(0.05)
            self.assertTrue(children)
            _kill_process_tree(parent.pid, grace_s=0.0)
            parent.wait(timeout=3)
            for child_pid in children:
                try:
                    os.kill(child_pid, 0)
                    self.fail(f"child {child_pid} still alive")
                except OSError:
                    pass
        finally:
            if parent.poll() is None:
                _kill_process_tree(parent.pid, grace_s=0.0)
                parent.wait(timeout=3)

    def test_list_child_pids_finds_direct_child(self) -> None:
        script = (
            "import subprocess, sys, time\n"
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            "time.sleep(30)\n"
        )
        parent = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 2.0
            children: list[int] = []
            while time.monotonic() < deadline:
                children = _list_child_pids(parent.pid)
                if children:
                    break
                time.sleep(0.05)
            self.assertTrue(children)
        finally:
            _kill_process_tree(parent.pid, grace_s=0.0)
            parent.wait(timeout=3)

    def test_terminate_child_processes_does_not_kill_self(self) -> None:
        with mock.patch("task_session._list_child_pids", return_value=[]):
            _terminate_child_processes()


if __name__ == "__main__":
    unittest.main()
