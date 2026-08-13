#!/usr/bin/env python3
"""Web run 阶段文案单测。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(WEB_AGENT_DIR))

from duration_history import classify_task_kind  # noqa: E402
from progress_message import resolve_task_estimate_seconds  # noqa: E402
from task_chain_estimate import analyze_task_chain  # noqa: E402
from web_run_phases import (  # noqa: E402
    PHASE_AGENT_CREATE,
    PHASE_BRIDGE_INIT,
    PHASE_MODEL_WAIT,
    PHASE_WORKER_READY,
)


class WebRunPhasesTests(unittest.TestCase):
    def test_phase_constants_non_empty(self) -> None:
        for value in (
            PHASE_WORKER_READY,
            PHASE_BRIDGE_INIT,
            PHASE_AGENT_CREATE,
            PHASE_MODEL_WAIT,
        ):
            self.assertTrue(value.strip())

    def test_moa_mutate_kind_and_estimate(self) -> None:
        prompt = "给 13311111111 发 100 钻石"
        kind = classify_task_kind(prompt)
        self.assertEqual(kind, "agent:moa_mutate")
        chain = analyze_task_chain(prompt, task_kind=kind)
        self.assertGreater(chain.total_seconds, 0)
        est = resolve_task_estimate_seconds(kind, prompt=prompt)
        self.assertIsNotNone(est)
        self.assertLess(est or 9999, 600)

    def test_moa_query_kind(self) -> None:
        kind = classify_task_kind("MOA 查手机号 13311111111 对应 userId")
        self.assertEqual(kind, "agent:moa_query")


if __name__ == "__main__":
    unittest.main()
