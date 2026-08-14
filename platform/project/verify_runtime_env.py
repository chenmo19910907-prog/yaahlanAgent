#!/usr/bin/env python3
"""runtime_env worker 环境合并回归测试。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from runtime_env import merge_worker_env  # noqa: E402


class RuntimeEnvWorkerTest(unittest.TestCase):
    def test_merge_worker_env_overrides_stale_inherited_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            admin_dir = Path(tmp) / "Admin"
            admin_dir.mkdir()
            env_file = admin_dir / ".env.local"
            env_file.write_text("ADMIN_SSO_TOKEN=fresh-from-file\n", encoding="utf-8")
            with mock.patch("runtime_env._WORKER_ENV_FILES", (env_file,)):
                with mock.patch.dict(os.environ, {"ADMIN_SSO_TOKEN": "stale-shell"}, clear=False):
                    merged = merge_worker_env()
            self.assertEqual(merged["ADMIN_SSO_TOKEN"], "fresh-from-file")


if __name__ == "__main__":
    unittest.main()
