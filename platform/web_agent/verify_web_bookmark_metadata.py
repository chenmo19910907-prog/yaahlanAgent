#!/usr/bin/env python3
"""web_bookmark_metadata 单测。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from web_bookmark_metadata import (  # noqa: E402
    _extract_html_metadata,
    _heuristic_metadata,
    resolve_bookmark_metadata,
)


class WebBookmarkMetadataTest(unittest.TestCase):
    def test_extract_html_metadata(self) -> None:
        html = """
        <html><head>
          <title>MOA 使用方法 - GitLab</title>
          <meta name="description" content="已登记 MOA 能力与命令" />
          <meta property="og:title" content="MOA 使用方法" />
        </head></html>
        """
        title, desc = _extract_html_metadata(html)
        self.assertIn("MOA", title)
        self.assertIn("MOA", desc)

    def test_heuristic_gitlab_blob(self) -> None:
        meta = _heuristic_metadata(
            "https://git.wemomo.com/soulchill-qa/auto-generate-testcase/-/blob/yaahlan/MOA/%E4%BD%BF%E7%94%A8%E6%96%B9%E6%B3%95.md"
        )
        self.assertEqual(meta["label"], "使用方法")
        self.assertIn("MOA", meta["description"])

    def test_heuristic_known_tunnel(self) -> None:
        meta = _heuristic_metadata("https://tunnel.wemomo.com")
        self.assertEqual(meta["label"], "Tunnel 抓包")
        self.assertIn("抓包", meta["description"])

    def test_resolve_without_fetch(self) -> None:
        with patch("web_bookmark_metadata.fetch_page_html", return_value=None):
            meta = resolve_bookmark_metadata("https://tunnel.wemomo.com", fetch_html=True)
        self.assertEqual(meta["label"], "Tunnel 抓包")

    def test_resolve_uses_page_title(self) -> None:
        html = "<html><head><title>家族 PK Showcase</title></head></html>"
        with patch("web_bookmark_metadata.fetch_page_html", return_value=html):
            meta = resolve_bookmark_metadata("http://172.18.125.90:18766/family-pk-showcase/")
        self.assertEqual(meta["label"], "家族 PK Showcase")
        self.assertEqual(meta["source"], "page_title")


if __name__ == "__main__":
    unittest.main()
