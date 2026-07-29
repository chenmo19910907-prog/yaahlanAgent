#!/usr/bin/env python3
"""server_watch 监视范围单测。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_AGENT_DIR))

from server_watch import _iter_watch_files, snapshot_mtimes  # noqa: E402


class ServerWatchTests(unittest.TestCase):
    def test_watch_includes_server_py(self) -> None:
        paths = {p.name for p in _iter_watch_files()}
        self.assertIn("server.py", paths)
        self.assertIn("chat.html", paths)

    def test_watch_excludes_data_dir(self) -> None:
        for path in _iter_watch_files():
            if WEB_AGENT_DIR in path.parents:
                rel = path.relative_to(WEB_AGENT_DIR)
                self.assertNotIn("data", rel.parts[:-1])

    def test_snapshot_is_stable(self) -> None:
        a = snapshot_mtimes()
        b = snapshot_mtimes()
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
