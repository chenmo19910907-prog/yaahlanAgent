#!/usr/bin/env python3
"""验收 UserAgentPool 模型切换：切换后须重建 Agent，不可复用旧窗口。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

GATEWAY_DIR = Path(__file__).resolve().parent
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

# 单元测试不依赖真实 cursor_sdk
if "cursor_sdk" not in sys.modules:
    cursor_sdk = MagicMock()
    cursor_sdk.Agent = MagicMock()
    cursor_sdk.AgentOptions = MagicMock()
    cursor_sdk.LocalAgentOptions = MagicMock()
    sys.modules["cursor_sdk"] = cursor_sdk

from user_agent_pool import UserAgentPool  # noqa: E402


class UserAgentPoolModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.index = Path(self.tmp.name) / "user_agents.json"
        self.pool = UserAgentPool(index_path=self.index)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _acquire(self, user_key: str, model: str) -> tuple[MagicMock, bool]:
        with patch("user_agent_pool.Agent") as agent_cls:
            agent_cls.create.return_value = MagicMock(agent_id=f"agent-{model}")
            agent_cls.resume.return_value = MagicMock(agent_id=f"resumed-{model}")
            agent, is_new = self.pool.acquire(
                user_key,
                api_key="test-key",
                workdir="/tmp",
                model=model,
                sender_name="tester",
                mcp_servers=None,
            )
        return agent, is_new

    def test_switch_model_rebuilds_even_when_persisted_model_empty(self) -> None:
        user_key = "web:test-session"
        self.index.write_text(
            json.dumps(
                {
                    user_key: {
                        "agent_id": "agent-old",
                        "sender_name": "Web-test",
                        "updated_at": "2026-07-28 00:00:00 UTC",
                    }
                }
            ),
            encoding="utf-8",
        )
        self.pool = UserAgentPool(index_path=self.index)

        agent1, _ = self._acquire(user_key, "composer-2.5")
        self.assertEqual(agent1.agent_id, "agent-composer-2.5")

        agent2, is_new2 = self._acquire(user_key, "composer-2.5-fast")
        self.assertTrue(is_new2)
        self.assertEqual(agent2.agent_id, "agent-composer-2.5-fast")

        saved = json.loads(self.index.read_text(encoding="utf-8"))
        self.assertEqual(saved[user_key]["model"], "composer-2.5-fast")

    def test_switch_model_closes_live_agent_in_memory(self) -> None:
        user_key = "web:live-session"
        agent1, _ = self._acquire(user_key, "composer-2.5")
        close_mock = agent1.close
        close_mock.reset_mock()

        agent2, is_new2 = self._acquire(user_key, "composer-2.5-fast")
        close_mock.assert_called_once()
        self.assertTrue(is_new2)
        self.assertEqual(agent2.agent_id, "agent-composer-2.5-fast")

    def test_same_model_reuses_live_agent(self) -> None:
        user_key = "web:reuse-session"
        agent1, _ = self._acquire(user_key, "composer-2.5")
        agent2, is_new2 = self._acquire(user_key, "composer-2.5")
        self.assertFalse(is_new2)
        self.assertIs(agent1, agent2)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(UserAgentPoolModelTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
