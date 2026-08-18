#!/usr/bin/env python3
"""Agent 任务超时时长：管理员 30 分钟，普通用户 10 分钟。"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path


def _timeout_constants() -> dict[str, int]:
    src = (
        Path(__file__).resolve().parents[1]
        / "dingtalk_gateway"
        / "cursor_runner.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(src)
    out: dict[str, int] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.endswith("_TIMEOUT_S"):
                out[target.id] = ast.literal_eval(node.value)
    return out


class TestAgentTimeout(unittest.TestCase):
    def test_timeout_constants(self) -> None:
        vals = _timeout_constants()
        self.assertEqual(vals["DEFAULT_TIMEOUT_S"], 600)
        self.assertEqual(vals["ADMIN_TIMEOUT_S"], 1800)


if __name__ == "__main__":
    unittest.main()
