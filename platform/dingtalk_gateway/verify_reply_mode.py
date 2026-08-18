"""离线验证钉钉回复详略切换（全员统一）。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

GATEWAY_DIR = Path(__file__).resolve().parent


class ReplyModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.index = Path(self.tmp.name) / "reply_mode.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_parse_reply_mode_request(self) -> None:
        from route_patterns import parse_reply_mode_request

        self.assertEqual(parse_reply_mode_request("精简回复"), "concise")
        self.assertEqual(parse_reply_mode_request("切换为标准回复"), "standard")
        self.assertEqual(parse_reply_mode_request("详细回复"), "detailed")
        self.assertEqual(parse_reply_mode_request("回复模式"), "query")
        self.assertIsNone(parse_reply_mode_request("查用户 12345"))

    def test_store_persists_global_mode(self) -> None:
        from reply_mode_store import ReplyModeStore

        store = ReplyModeStore(index_path=self.index)
        store.set("concise")
        reloaded = ReplyModeStore(index_path=self.index)
        self.assertEqual(reloaded.get(), "concise")

    def test_store_default_standard(self) -> None:
        from reply_mode_store import ReplyModeStore

        store = ReplyModeStore(index_path=self.index)
        self.assertEqual(store.get(), "standard")

    def test_handle_reply_mode_message(self) -> None:
        from reply_mode_route import handle_reply_mode_message
        from reply_mode_store import ReplyModeStore

        with patch("reply_mode_route.get_reply_mode_store") as mocked:
            store = ReplyModeStore(index_path=self.index)
            mocked.return_value = store
            ack = handle_reply_mode_message("精简回复")
            self.assertIn("精简回复", ack or "")
            self.assertIn("全员统一", ack or "")
            self.assertEqual(store.get(), "concise")
            query = handle_reply_mode_message("回复模式")
            self.assertIn("精简回复", query or "")
            self.assertIn("全员统一", query or "")

    def test_gateway_prompt_injects_concise_instruction(self) -> None:
        from gateway_prompt import build_gateway_prompt

        prompt = build_gateway_prompt("查用户", reply_mode="concise")
        self.assertIn("回复详略（精简）", prompt)


if __name__ == "__main__":
    unittest.main()
