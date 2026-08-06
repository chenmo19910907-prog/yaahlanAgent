#!/usr/bin/env python3
"""Web Agent 代码修改权限：管理员可改代码，MOA 入库全员可用。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
for path in (GATEWAY_DIR, WEB_AGENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from code_modify_permission import looks_like_code_modify_request  # noqa: E402
from web_prompt import build_web_prompt  # noqa: E402


class WebCodeModifyPermissionTest(unittest.TestCase):
    def test_moa_registry_not_code_modify(self) -> None:
        prompt = "帮我把MOA入库，录制跨房 PK 邀请"
        self.assertFalse(looks_like_code_modify_request(prompt))

    def test_gateway_change_is_code_modify(self) -> None:
        prompt = "修改 platform/web_agent/server.py 增加健康检查"
        self.assertTrue(looks_like_code_modify_request(prompt))

    def test_readonly_prompt_includes_moa_open(self) -> None:
        text = build_web_prompt(
            "查询用户详情",
            is_new_session=True,
            allow_code_modify=False,
            allow_moa_registry=True,
        )
        self.assertIn("可 MOA 入库", text)
        self.assertIn("工具台 MOA 录制", text)

    def test_admin_prompt_no_readonly_banner(self) -> None:
        text = build_web_prompt(
            "查询用户详情",
            is_new_session=True,
            allow_code_modify=True,
        )
        self.assertNotIn("【只读模式】", text)
        self.assertIn("代码修改权限", text)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(WebCodeModifyPermissionTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print("[PASS] verify_web_code_modify")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
