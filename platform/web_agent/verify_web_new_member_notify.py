#!/usr/bin/env python3
"""Web Agent 新成员超管通知离线验证。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
for d in (GATEWAY_DIR, WEB_AGENT_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

import web_new_member_notify as notify  # noqa: E402


class WebNewMemberNotifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.known_path = Path(self.tmp.name) / "known_agent_users.json"
        self.lock_path = Path(self.tmp.name) / ".known_agent_users.lock"
        self._orig_known = notify.KNOWN_USERS_PATH
        self._orig_lock = notify.LOCK_PATH
        self._orig_bootstrap = notify._bootstrap_done
        notify.KNOWN_USERS_PATH = self.known_path
        notify.LOCK_PATH = self.lock_path
        notify._bootstrap_done = False

    def tearDown(self) -> None:
        notify.KNOWN_USERS_PATH = self._orig_known
        notify.LOCK_PATH = self._orig_lock
        notify._bootstrap_done = self._orig_bootstrap

    def test_build_message(self) -> None:
        text = notify.build_new_member_message(display_name="张三", staff_id="u1")
        self.assertIn("张三", text)
        self.assertIn("新成员", text)

    def test_dingtalk_conversation_keys(self) -> None:
        root = Path(self.tmp.name)
        conv = root / "dingtalk_gateway" / "data" / "conversations.json"
        conv.parent.mkdir(parents=True, exist_ok=True)
        conv.write_text(
            json.dumps(
                {
                    "dm:staff_a": {"prompt": "hi"},
                    "cid123:user:staff_b": {"prompt": "hello"},
                }
            ),
            encoding="utf-8",
        )
        orig = notify.WEB_AGENT_DIR
        notify.WEB_AGENT_DIR = root / "web_agent"
        try:
            ids = notify._staff_ids_from_dingtalk_conversations()
        finally:
            notify.WEB_AGENT_DIR = orig
        self.assertEqual(ids, {"staff_a", "staff_b"})

    @patch("web_new_member_notify._notify_super_admins", return_value=2)
    @patch("web_new_member_notify._ensure_bootstrap_locked")
    def test_first_use_notifies(
        self,
        _bootstrap: unittest.mock.MagicMock,
        mock_notify: unittest.mock.MagicMock,
    ) -> None:
        ok = notify.maybe_notify_new_member(staff_id="user_a", display_name="用户A")
        self.assertTrue(ok)
        mock_notify.assert_called_once()
        ok2 = notify.maybe_notify_new_member(staff_id="user_a", display_name="用户A")
        self.assertFalse(ok2)

    @patch("web_new_member_notify._notify_super_admins")
    @patch("web_admin_notify._can_notify_staff", return_value=False)
    @patch("web_new_member_notify._ensure_bootstrap_locked")
    def test_guest_skipped(
        self,
        _bootstrap: unittest.mock.MagicMock,
        _can: unittest.mock.MagicMock,
        mock_notify: unittest.mock.MagicMock,
    ) -> None:
        ok = notify.maybe_notify_new_member(staff_id="guest_x", display_name="访客")
        self.assertFalse(ok)
        mock_notify.assert_not_called()


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(WebNewMemberNotifyTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("[PASS] verify_web_new_member_notify")


if __name__ == "__main__":
    main()
