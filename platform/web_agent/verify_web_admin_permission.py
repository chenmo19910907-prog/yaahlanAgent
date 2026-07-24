#!/usr/bin/env python3
"""web_admin_permission 单测。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(WEB_AGENT_DIR))

from web_admin_permission import (  # noqa: E402
    DENY_MESSAGE,
    is_web_admin,
    web_admin_denial_message,
)


class WebAdminPermissionTest(unittest.TestCase):
    def test_allowed_staff_id(self) -> None:
        with patch(
            "web_admin_permission.is_code_modify_allowed",
            return_value=True,
        ):
            self.assertTrue(is_web_admin(staff_id="32274159141215328"))

    def test_denied_staff_id(self) -> None:
        with patch(
            "web_admin_permission.is_code_modify_allowed",
            return_value=False,
        ):
            self.assertFalse(is_web_admin(staff_id="999"))

    def test_empty_staff_id(self) -> None:
        self.assertFalse(is_web_admin(staff_id=""))
        self.assertFalse(is_web_admin(staff_id=None))

    def test_denial_message(self) -> None:
        self.assertEqual(web_admin_denial_message(), DENY_MESSAGE)


if __name__ == "__main__":
    unittest.main()
