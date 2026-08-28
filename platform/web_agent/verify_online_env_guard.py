#!/usr/bin/env python3
"""线上环境操作权限：全员只读查询；其余线上 MOA 全员禁止（含管理员）；其他线上操作仅管理员。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parents[1] / "dingtalk_gateway"
WEB_AGENT_DIR = Path(__file__).resolve().parent
for path in (GATEWAY_DIR, WEB_AGENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from online_env_guard import (  # noqa: E402
    looks_like_online_env_request,
    looks_like_online_moa_forbidden_request,
    looks_like_online_public_query_request,
    online_env_denial_message,
    online_moa_denial_message,
    resolve_online_env_denial,
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

    def test_public_admin_query_allowed(self) -> None:
        self.assertTrue(looks_like_online_public_query_request("线上环境查用户 107427060"))

    def test_public_moa_phone_query_allowed(self) -> None:
        self.assertTrue(
            looks_like_online_public_query_request("线上环境查手机号 13311111111")
        )

    def test_public_query_not_moa_forbidden(self) -> None:
        self.assertFalse(
            looks_like_online_moa_forbidden_request("线上环境查用户 107427060")
        )

    def test_online_vip_moa_forbidden(self) -> None:
        self.assertTrue(
            looks_like_online_moa_forbidden_request("线上环境13311111111添加vip8")
        )

    def test_online_moa_script_forbidden(self) -> None:
        self.assertTrue(
            looks_like_online_moa_forbidden_request(
                "python3 MOA/moa_execute.py --target-environment prod --vip-level 8"
            )
        )

    def test_resolve_public_query_non_admin(self) -> None:
        self.assertIsNone(
            resolve_online_env_denial(
                "线上环境查用户 107427060",
                online_admin_allowed=False,
            )
        )

    def test_resolve_moa_mutation_non_admin(self) -> None:
        msg = resolve_online_env_denial(
            "线上环境13311111111添加vip8",
            online_admin_allowed=False,
        )
        self.assertEqual(msg, online_moa_denial_message())

    def test_resolve_moa_mutation_admin(self) -> None:
        msg = resolve_online_env_denial(
            "线上环境13311111111添加vip8",
            online_admin_allowed=True,
        )
        self.assertEqual(msg, online_moa_denial_message())

    def test_resolve_tunnel_non_admin(self) -> None:
        msg = resolve_online_env_denial(
            "线上环境 tunnel 查 107427060 抓包",
            online_admin_allowed=False,
        )
        self.assertEqual(msg, online_env_denial_message())

    def test_denial_message(self) -> None:
        msg = online_env_denial_message()
        self.assertIn("线上环境", msg)
        self.assertIn("管理员列表", msg)
        self.assertIn("申请管理员", msg)
        self.assertIn("用户头像信息", msg)

    def test_moa_denial_message(self) -> None:
        msg = online_moa_denial_message()
        self.assertIn("Admin-查询用户详情", msg)
        self.assertIn("MOA-按手机号查 userId", msg)

    def test_readonly_prompt_includes_public_query(self) -> None:
        text = build_web_prompt(
            "查询用户详情",
            is_new_session=True,
            allow_code_modify=False,
            allow_online_env_operation=False,
            allow_online_public_query=True,
        )
        self.assertIn("Admin-查询用户详情", text)
        self.assertIn("MOA-按手机号查 userId", text)
        self.assertIn("其他线上 MOA", text)

    def test_admin_prompt_includes_online(self) -> None:
        text = build_web_prompt(
            "查询用户详情",
            is_new_session=True,
            allow_code_modify=True,
            allow_online_env_operation=True,
        )
        self.assertIn("线上环境", text)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OnlineEnvGuardTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print("[PASS] verify_online_env_guard")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
