#!/usr/bin/env python3
"""web_file_store / web_share_file 单元测试。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from web_file_store import (  # noqa: E402
    FileUploadError,
    consume_pending_outputs,
    parse_web_user_key,
    register_output_file,
    resolve_upload_file,
    save_chat_attachments,
)


class WebFileStoreTests(unittest.TestCase):
    def test_parse_web_user_key(self) -> None:
        self.assertEqual(parse_web_user_key("web:abc123"), "abc123")
        self.assertIsNone(parse_web_user_key("dm:123"))

    def test_save_chat_attachments_mixed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            uploads = Path(tmp) / "uploads"
            outputs = Path(tmp) / "outputs"
            import web_file_store as store

            store.UPLOADS_DIR = uploads
            store.OUTPUTS_DIR = outputs
            png = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
                b"\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            import base64

            saved = save_chat_attachments(
                "sess1",
                [
                    {
                        "name": "shot.png",
                        "mime": "image/png",
                        "data_base64": base64.b64encode(png).decode("ascii"),
                    },
                    {
                        "name": "data.csv",
                        "mime": "text/csv",
                        "data_base64": base64.b64encode(b"a,b\n1,2").decode("ascii"),
                    },
                ],
            )
            self.assertEqual(len(saved), 2)
            self.assertEqual(saved[0].kind, "image")
            self.assertEqual(saved[1].kind, "file")
            self.assertIsNotNone(resolve_upload_file("sess1", saved[1].stored_name))

    def test_register_and_consume_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            uploads = Path(tmp) / "uploads"
            outputs = Path(tmp) / "outputs"
            import web_file_store as store

            store.UPLOADS_DIR = uploads
            store.OUTPUTS_DIR = outputs
            src = Path(tmp) / "report.txt"
            src.write_text("hello", encoding="utf-8")
            item = register_output_file("sess2", src, display_name="结果.txt")
            self.assertTrue(item.api_path.startswith("/api/outputs/sess2/"))
            pending = consume_pending_outputs("sess2")
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0].original_name, "结果.txt")
            self.assertEqual(consume_pending_outputs("sess2"), [])

    def test_reject_unsupported_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            uploads = Path(tmp) / "uploads"
            outputs = Path(tmp) / "outputs"
            import web_file_store as store

            store.UPLOADS_DIR = uploads
            store.OUTPUTS_DIR = outputs
            src = Path(tmp) / "bad.exe"
            src.write_bytes(b"MZ")
            with self.assertRaises(FileUploadError):
                register_output_file("sess3", src)


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(WebFileStoreTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("[PASS] verify_web_file_store")


if __name__ == "__main__":
    main()
