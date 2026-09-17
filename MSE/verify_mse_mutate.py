#!/usr/bin/env python3
"""MSE mutate API 单测。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

MSE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MSE_DIR))

from mse.mutate import parse_mse_error, plan_config_patch  # noqa: E402


class MseMutateTests(unittest.TestCase):
    def test_parse_permission_error(self) -> None:
        msg = "创建发布记录失败: ec=300, em=没有 appKey: foo nameSpace: bar在集群: stage 的操作权限"
        ec, em, code = parse_mse_error(msg)
        self.assertEqual(ec, 300)
        self.assertIn("appKey", em or "")
        self.assertEqual(code, "mse_permission_denied")

    def test_plan_config_patch(self) -> None:
        item = {"configValue": '{"a": 1, "b": 2}', "activeName": "json"}
        new_value, changes, current = plan_config_patch(item, {"a": 3})
        self.assertEqual(current, '{"a": 1, "b": 2}')
        self.assertIn('"a": 3', new_value)
        self.assertEqual(len(changes), 1)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
