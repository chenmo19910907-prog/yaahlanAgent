#!/usr/bin/env python3
"""MOA 试跑成功后自动入库 registry 的单元测试。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

_MOA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _MOA)

from moa.registry_sync import (  # noqa: E402
    refresh_platform_workbench,
    template_basename_from_payload_file,
    template_needs_sync,
)


class TestAutoSyncRegistry(unittest.TestCase):
    def test_template_basename_from_payload_file(self) -> None:
        templates = os.path.join(_MOA, "templates")
        inside = os.path.join(templates, "VIP-增加经验值.json")
        self.assertEqual(template_basename_from_payload_file(inside), "VIP-增加经验值.json")
        self.assertIsNone(template_basename_from_payload_file("/tmp/foo.json"))
        self.assertIsNone(template_basename_from_payload_file(None))

    def test_registered_template_skips_sync(self) -> None:
        self.assertFalse(template_needs_sync("VIP-增加经验值.json"))

    def test_unregistered_template_needs_sync(self) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".json",
            dir=os.path.join(_MOA, "templates"),
            delete=False,
        ) as f:
            fname = os.path.basename(f.name)
        try:
            self.assertTrue(template_needs_sync(fname))
        finally:
            os.unlink(os.path.join(_MOA, "templates", fname))

    def test_refresh_platform_workbench(self) -> None:
        from unittest import mock

        with mock.patch("moa.registry_sync.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0)
            refresh_platform_workbench(quiet=True)
            run.assert_called_once()
            cmd = run.call_args[0][0]
            self.assertIn("after_registry_update.py", cmd[-2])
            self.assertEqual(cmd[-1], "--quiet")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
