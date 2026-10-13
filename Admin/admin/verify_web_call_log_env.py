#!/usr/bin/env python3
"""Admin 操作记录环境判定单测。"""

from __future__ import annotations

import unittest

from web_call_log import (  # noqa: E402
    _admin_environment_from_request,
    _environment_from_account_summary,
)


class AdminCallLogEnvTest(unittest.TestCase):
    def test_staging_url_is_test_even_with_online_auth(self) -> None:
        url = "https://yaahlan-admin-alpha.wemomo.com/admin/user/queryUserDetail"
        self.assertEqual(
            _admin_environment_from_request(url, auth="yaahlan_online"),
            "test",
        )

    def test_online_url_is_online(self) -> None:
        url = "https://yaahlan-admin.wemomo.com/admin/user/queryUserDetail"
        self.assertEqual(
            _admin_environment_from_request(url, auth="yaahlan"),
            "online",
        )

    def test_account_test_user_id(self) -> None:
        self.assertEqual(_environment_from_account_summary("100486375"), "test")
        self.assertEqual(_environment_from_account_summary("100486375 等 5 个账号"), "test")

    def test_account_online_user_id(self) -> None:
        self.assertEqual(_environment_from_account_summary("107347491"), "online")


if __name__ == "__main__":
    unittest.main()
