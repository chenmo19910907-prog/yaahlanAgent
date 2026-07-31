#!/usr/bin/env python3
"""server_watch 监视范围单测。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_AGENT_DIR))

from server_watch import (  # noqa: E402
    WEB_AGENT_DIR,
    _has_restart_worthy_changes,
    _is_ignored_watch_path,
    _iter_watch_files,
    snapshot_mtimes,
)


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

    def test_watch_excludes_keynote_dir(self) -> None:
        for path in _iter_watch_files():
            if WEB_AGENT_DIR in path.parents:
                rel = path.relative_to(WEB_AGENT_DIR)
                self.assertNotIn("keynote", rel.parts[:-1])
        names = {p.name for p in _iter_watch_files()}
        self.assertNotIn("scenes.json", names)

    def test_keynote_path_is_ignored_for_restart(self) -> None:
        keynote_html = WEB_AGENT_DIR / "keynote" / "preview.html"
        self.assertTrue(_is_ignored_watch_path(keynote_html))

    def test_chat_html_change_is_restart_worthy(self) -> None:
        chat_html = WEB_AGENT_DIR / "chat.html"
        self.assertFalse(_is_ignored_watch_path(chat_html))

    def test_only_keynote_changes_do_not_restart(self) -> None:
        old = {str(WEB_AGENT_DIR / "chat.html"): 1.0}
        new = {
            str(WEB_AGENT_DIR / "chat.html"): 1.0,
            str(WEB_AGENT_DIR / "keynote" / "preview.html"): 2.0,
        }
        self.assertFalse(_has_restart_worthy_changes(old, new))

    def test_mixed_changes_restart(self) -> None:
        old = {str(WEB_AGENT_DIR / "chat.html"): 1.0}
        new = {str(WEB_AGENT_DIR / "chat.html"): 2.0}
        self.assertTrue(_has_restart_worthy_changes(old, new))

    def test_snapshot_is_stable(self) -> None:
        a = snapshot_mtimes()
        b = snapshot_mtimes()
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
