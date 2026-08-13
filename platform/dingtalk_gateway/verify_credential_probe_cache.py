#!/usr/bin/env python3
"""credential_probe_cache 单测。"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

GATEWAY_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(GATEWAY_DIR))

from credential_probe_cache import cached_probe, get_cached, invalidate_cached, set_cached


class CredentialProbeCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        invalidate_cached()

    def test_cached_probe_reuses_within_ttl(self) -> None:
        calls = {"n": 0}

        def probe() -> tuple[bool, str]:
            calls["n"] += 1
            return True, "ok"

        with mock.patch.dict(os.environ, {"CREDENTIAL_PROBE_CACHE_TTL": "60"}, clear=False):
            self.assertEqual(cached_probe("moa", probe), (True, "ok"))
            self.assertEqual(cached_probe("moa", probe), (True, "ok"))
        self.assertEqual(calls["n"], 1)

    def test_force_bypasses_cache(self) -> None:
        calls = {"n": 0}

        def probe() -> tuple[bool, str]:
            calls["n"] += 1
            return True, "ok"

        with mock.patch.dict(os.environ, {"CREDENTIAL_PROBE_CACHE_TTL": "60"}, clear=False):
            cached_probe("admin", probe)
            cached_probe("admin", probe, force=True)
        self.assertEqual(calls["n"], 2)

    def test_zero_ttl_disables_cache(self) -> None:
        calls = {"n": 0}

        def probe() -> tuple[bool, str]:
            calls["n"] += 1
            return False, "x"

        with mock.patch.dict(os.environ, {"CREDENTIAL_PROBE_CACHE_TTL": "0"}, clear=False):
            cached_probe("tunnel", probe)
            cached_probe("tunnel", probe)
        self.assertEqual(calls["n"], 2)

    def test_set_and_get_cached(self) -> None:
        with mock.patch.dict(os.environ, {"CREDENTIAL_PROBE_CACHE_TTL": "30"}, clear=False):
            set_cached("k", (True, "cached"))
            self.assertEqual(get_cached("k"), (True, "cached"))


if __name__ == "__main__":
    unittest.main()
