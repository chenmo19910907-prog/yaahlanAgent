#!/usr/bin/env python3
"""web_docs.json 单测。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

WEB_DOCS_PATH = Path(__file__).resolve().parent / "config" / "web_docs.json"


class WebDocsTest(unittest.TestCase):
    def test_web_docs_file_exists(self) -> None:
        self.assertTrue(WEB_DOCS_PATH.is_file())

    def test_web_docs_has_categories(self) -> None:
        data = json.loads(WEB_DOCS_PATH.read_text(encoding="utf-8"))
        self.assertIn("title", data)
        self.assertIn("intro", data)
        categories = data.get("categories")
        self.assertIsInstance(categories, list)
        self.assertGreater(len(categories), 0)
        first = categories[0]
        self.assertIn("name", first)
        items = first.get("items")
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0)
        self.assertIn("url", items[0])
        self.assertIn("title", items[0])


if __name__ == "__main__":
    unittest.main()
