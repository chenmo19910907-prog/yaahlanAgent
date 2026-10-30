#!/usr/bin/env python3
"""web_service_restart 单元测试。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from web_service_restart import ServiceRestartResult, execute_service_restart


class WebServiceRestartTests(unittest.TestCase):
    def test_unknown_target(self) -> None:
        result = execute_service_restart(target="unknown", silent=True)
        self.assertFalse(result.ok)
        self.assertIn("target", result.message)

    @patch("web_service_restart._count_active_worker_runs", return_value=2)
    def test_web_agent_blocks_when_tasks_active(self, _mock: MagicMock) -> None:
        result = execute_service_restart(target="web_agent", silent=True)
        self.assertFalse(result.ok)
        self.assertIn("2", result.message)

    @patch("web_service_restart.threading.Thread")
    @patch("web_service_restart._count_active_worker_runs", return_value=0)
    def test_web_agent_schedules_restart(self, _active: MagicMock, thread_cls: MagicMock) -> None:
        result = execute_service_restart(target="web_agent", silent=False)
        self.assertTrue(result.ok)
        thread_cls.assert_called_once()

    @patch("web_service_restart.subprocess.run")
    @patch("web_service_restart.GATEWAY_CTL")
    def test_gateway_silent_restart_ok(self, ctl: MagicMock, run: MagicMock) -> None:
        ctl.is_file.return_value = True
        run.return_value = MagicMock(returncode=0, stdout="[OK] 已静默重启\n", stderr="")
        result = execute_service_restart(target="dingtalk_gateway", silent=True)
        self.assertTrue(result.ok)
        run.assert_called_once()
        args = run.call_args[0][0]
        self.assertEqual(args[-1], "silent-restart")

    @patch("web_service_restart.subprocess.run")
    @patch("web_service_restart.GATEWAY_CTL")
    def test_gateway_normal_restart(self, ctl: MagicMock, run: MagicMock) -> None:
        ctl.is_file.return_value = True
        run.return_value = MagicMock(returncode=0, stdout="[OK] 已重启\n", stderr="")
        result = execute_service_restart(target="dingtalk_gateway", silent=False)
        self.assertTrue(result.ok)
        args = run.call_args[0][0]
        self.assertEqual(args[-1], "restart")


if __name__ == "__main__":
    unittest.main()
