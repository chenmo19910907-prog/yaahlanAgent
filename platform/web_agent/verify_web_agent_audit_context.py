#!/usr/bin/env python3
"""web_agent_audit_context 单测：子进程无 env 时钉钉 active 回退。"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(WEB_AGENT_DIR))

from web_agent_audit_context import (  # noqa: E402
    ACTIVE_PATH,
    AUDIT_DIR,
    hydrate_audit_env_from_store,
    resolve_audit_context,
)


class WebAgentAuditContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        audit_dir = Path(self.tmp.name) / "audit_context"
        audit_dir.mkdir(parents=True)
        self.active = audit_dir / "active.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_subprocess_picks_fresh_dingtalk_active_without_env_hints(self) -> None:
        snap = {
            "batch_key": "cidx:user:034053666132897501",
            "run_id": "dingtalk:msgExample",
            "operator_staff_id": "034053666132897501",
            "operator_name": "范其乐",
            "source": "dingtalk",
            "updated_epoch": time.time(),
        }
        self.active.write_text(json.dumps(snap), encoding="utf-8")
        with patch("web_agent_audit_context.AUDIT_DIR", self.active.parent):
            with patch("web_agent_audit_context.ACTIVE_PATH", self.active):
                with patch.dict("os.environ", {}, clear=True):
                    self.assertTrue(hydrate_audit_env_from_store())
                    ctx = resolve_audit_context()
        self.assertIsNotNone(ctx)
        assert ctx is not None
        self.assertEqual(ctx["operator_name"], "范其乐")
        self.assertEqual(ctx["run_id"], "dingtalk:msgExample")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
