#!/usr/bin/env python3
"""bookmarks_store 单测。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from bookmarks_store import load_bookmarks, merge_legacy_bookmarks, normalize_bookmarks_payload  # noqa: E402


class BookmarksStoreTest(unittest.TestCase):
    def test_merge_skips_duplicate_url(self) -> None:
        team = load_bookmarks()
        legacy = {
            "categories": [{"id": "mine", "label": "我的收藏"}],
            "items": [
                {
                    "id": "x1",
                    "label": "能力目录",
                    "url": "http://127.0.0.1:18765/catalog.html",
                    "categoryId": "platform",
                },
                {
                    "id": "x2",
                    "label": "新站点",
                    "url": "https://example.test/only-me",
                    "categoryId": "mine",
                },
            ],
        }
        merged, added = merge_legacy_bookmarks(team, legacy)
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["url"], "https://example.test/only-me")
        self.assertIsNotNone(normalize_bookmarks_payload(merged))


if __name__ == "__main__":
    unittest.main()
