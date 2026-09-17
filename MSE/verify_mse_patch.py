#!/usr/bin/env python3
"""MSE patch 与写入参数单测。"""

from __future__ import annotations

import sys
import unittest

MSE_DIR = __import__("pathlib").Path(__file__).resolve().parent
sys.path.insert(0, str(MSE_DIR))

from mse.patch import apply_set_args, parse_scalar  # noqa: E402


class MsePatchTests(unittest.TestCase):
    def test_parse_scalar_json(self) -> None:
        self.assertEqual(parse_scalar("123"), 123)
        self.assertEqual(parse_scalar("true"), True)
        self.assertEqual(parse_scalar("hello"), "hello")

    def test_apply_set_args(self) -> None:
        updated, changes = apply_set_args({"a": 1, "b": 2}, ["a=3", 'c="x"'])
        self.assertEqual(updated, {"a": 3, "b": 2, "c": "x"})
        self.assertEqual(len(changes), 2)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
