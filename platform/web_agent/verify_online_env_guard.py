#!/usr/bin/env python3
"""线上环境操作权限：仅管理员可执行。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

GATEWAY_DIR = Path(__file__).resolve().parents[1] / "dingtalk_gateway"
WEB_AGENT_DIR = Path(__file__).resolve().parent
for path in (GATEWAY_DIR, WEB_AGENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from online_env_guard import (  # noqa: E402
    looks_like_online_env_request,
    online_env_denial_message,
)
from web_prompt import build_web_prompt  # noqa: E402


class OnlineEnvGuardTest(unittest.TestCase):
    def test_online_account_upgrade_detected(self) -> None:
        prompt = "线上账号107427060，升级VIP1"
        self.assertTrue(looks_like_online_env_request(prompt))

    def test_online_env_query_detected(self) -> None:
        self.assertTrue(looks_like_online_env_request("线上环境查用户 107427060"))

    def test_normal_stage_query_not_blocked(self) -> None:
        self.assertFalse(looks_like_online_env_request("100465989升级 VIP3"))
        self.assertFalse(looks_like_online_env_request("查询13311111111的用户信息"))

    def test_env_comparison_question_not_blocked(self) -> None:
        self.assertFalse(looks_like_online_env_request("这个是正式环境还是测试环境"))

    def test_policy_discussion_not_blocked(self) -> None:
        text = "增加规则，凡是涉及线上环境线上账号线上等操作一律只有管理员可以操作"
        self.assertFalse(looks_like_online_env_request(text))

    def test_online_execute_script_detected(self) -> None:
        self.assertTrue(
            looks_like_online_env_request(
                "python3 online/online_execute.py admin --query-user-id 107427060"
            )
        )

    def test_denial_message(self) -> None:
        msg = online_env_denial_message()
        self.assertIn("线上环境", msg)
        self.assertIn("申请管理员", msg)
        self.assertNotIn("原因", msg)

    def test_readonly_prompt_excludes_online(self) -> None:
        text = build_web_prompt(
            "查询用户详情",
            is_new_session=True,
            allow_code_modify=False,
            allow_online_env_operation=False,
        )
        self.assertIn("不含", text)
        self.assertIn("线上环境", text)

    def test_admin_prompt_includes_online(self) -> None:
        text = build_web_prompt(
            "查询用户详情",
            is_new_session=True,
            allow_code_modify=True,
            allow_online_env_operation=True,
        )
        self.assertIn("线上环境操作", text)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OnlineEnvGuardTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print("[PASS] verify_online_env_guard")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
