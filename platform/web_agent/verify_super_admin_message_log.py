#!/usr/bin/env python3
"""超管私聊发送记录存储离线验证。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

import web_super_admin_message_log as log_mod  # noqa: E402


class SuperAdminMessageLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._log_path = Path(self._tmpdir.name) / "super_admin_message_log.json"
        self._audit_path = Path(self._tmpdir.name) / "super_admin_message_log_audit.jsonl"
        patcher = patch.object(log_mod, "LOG_PATH", self._log_path)
        self.addCleanup(patcher.stop)
        patcher.start()
        audit_patcher = patch.object(log_mod, "AUDIT_JSONL_PATH", self._audit_path)
        self.addCleanup(audit_patcher.stop)
        audit_patcher.start()
        noop = patch.object(log_mod, "_maybe_backfill_once", lambda: None)
        self.addCleanup(noop.stop)
        noop.start()
        log_mod._LOG_FLOCK_FD = None
        log_mod._BACKFILL_ONCE_DONE = False

    def test_append_and_list_desc(self) -> None:
        log_mod.append_super_admin_message_log(
            operator_staff_id="op1",
            operator_label="陈墨",
            target_staff_id="t1",
            target_label="用户A",
            message="第一条",
            sent_at="2026-01-01T00:00:00+00:00",
        )
        log_mod.append_super_admin_message_log(
            operator_staff_id="op1",
            operator_label="陈墨",
            target_staff_id="t1",
            target_label="用户A",
            message="第二条",
            sent_at="2026-01-02T00:00:00+00:00",
        )
        log_mod.append_super_admin_message_log(
            operator_staff_id="op1",
            operator_label="陈墨",
            target_staff_id="t2",
            target_label="用户B",
            message="其他用户",
            sent_at="2026-01-03T00:00:00+00:00",
        )
        payload = log_mod.list_super_admin_message_entries(target_staff_id="t1")
        self.assertEqual(payload["total"], 2)
        messages = [row["message"] for row in payload["entries"]]
        self.assertEqual(messages, ["第二条", "第一条"])
        self.assertTrue(self._log_path.is_file())
        data = json.loads(self._log_path.read_text(encoding="utf-8"))
        self.assertEqual(len(data), 3)

    def test_merge_backfill_idempotent(self) -> None:
        rows = [
            {
                "sentAt": "2026-10-22T03:21:22+00:00",
                "targetStaffId": "32274159141215328",
                "message": "测试",
                "backfillKey": "k1",
            }
        ]
        self.assertEqual(log_mod.merge_backfill_entries(rows), 1)
        self.assertEqual(log_mod.merge_backfill_entries(rows), 0)
        payload = log_mod.list_super_admin_message_entries()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["entries"][0]["message"], "测试")
        self.assertEqual(payload["entries"][0].get("source"), "backfill")


if __name__ == "__main__":
    unittest.main()
