#!/usr/bin/env python3
"""Web 端「重启 Web Agent」须 SSE done（不落盘中间回复），再异步 restart.py 落盘最终结果。"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
for p in (str(GATEWAY_DIR), str(WEB_AGENT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


class WebAgentRestartDeferTest(unittest.TestCase):
    def test_command_router_defers_when_run_id_set(self) -> None:
        from command_router import try_route

        with patch.dict(os.environ, {"WEB_AGENT_RUN_ID": "abc123"}, clear=False):
            result = try_route("重启web agent")
        self.assertTrue(result.handled)
        self.assertTrue(result.defer_web_agent_restart)
        self.assertEqual(result.task_kind, "web_agent_restart")
        self.assertEqual(result.output, "")

    def test_command_router_sync_without_run_id(self) -> None:
        from command_router import try_route
        from web_agent_restart import WebAgentRestartOutcome

        env = os.environ.copy()
        env.pop("WEB_AGENT_RUN_ID", None)
        with patch.dict(os.environ, env, clear=True):
            with patch(
                "command_router.force_restart_web_agent",
                return_value=WebAgentRestartOutcome(True, "端口 18766 健康检查通过。"),
            ):
                result = try_route("重启web agent")
        self.assertTrue(result.handled)
        self.assertFalse(result.defer_web_agent_restart)
        self.assertIn("Web Agent 已重启完成", result.output)

    def test_append_deferred_restart_followup(self) -> None:
        from web_agent_restart import WebAgentRestartOutcome, append_deferred_restart_followup

        with patch("web_session_store.get_session_store") as mock_store:
            append_deferred_restart_followup(
                "sess123",
                WebAgentRestartOutcome(True, "端口 18766 健康检查通过。"),
            )
        mock_store.return_value.append_message.assert_called_once()
        args = mock_store.return_value.append_message.call_args[0]
        self.assertEqual(args[0], "sess123")
        self.assertEqual(args[1], "assistant")
        self.assertIn("Web Agent 已重启完成", args[2])


if __name__ == "__main__":
    unittest.main()
