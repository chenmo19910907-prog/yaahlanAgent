#!/usr/bin/env python3
"""MOA client 鉴权失败自动刷新单测。"""

from __future__ import annotations

import json
import os
import sys
import unittest
import unittest.mock
from pathlib import Path

MOA_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MOA_DIR))

from moa.client import (  # noqa: E402
    MoaClient,
    _is_auth_body,
    _is_auth_error,
    http_post_json,
)


class MoaAuthRefreshTests(unittest.TestCase):
    def test_is_auth_body_detects_aegis_html(self) -> None:
        body = "<!doctype html><title>Aegis SSO_MSE管理平台</title>"
        self.assertTrue(_is_auth_body(body))

    def test_is_auth_error_http_401(self) -> None:
        self.assertTrue(_is_auth_error(401, "Unauthorized"))

    def test_http_post_json_retries_after_auth_html(self) -> None:
        html = "<!doctype html><title>Aegis SSO_MSE管理平台</title>"
        calls = {"count": 0}

        def fake_urlopen(req, timeout=0):
            calls["count"] += 1
            if calls["count"] == 1:

                class Resp:
                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        return False

                    def read(self):
                        return html.encode()

                return Resp()

            class Resp:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def read(self):
                    return json.dumps({"ec": 0, "result": {"ec": 0, "em": "ok"}}).encode()

            return Resp()

        with unittest.mock.patch("moa.client.urllib.request.urlopen", side_effect=fake_urlopen), unittest.mock.patch(
            "moa.client._try_auto_refresh_moa", return_value=True
        ), unittest.mock.patch.dict("os.environ", {"MOA_COOKIE": "refreshed_cookie=1"}, clear=False):
            result = http_post_json(
                "https://mse.wemomo.com/httpproxy/moa/test/execute",
                "old_cookie=0",
                {"method": "ping"},
                1.0,
            )

        self.assertEqual(calls["count"], 2)
        self.assertEqual(result["ec"], 0)

    def test_moa_client_syncs_refreshed_cookie(self) -> None:
        def fake_post(*_args, **_kwargs):
            os.environ["MOA_COOKIE"] = "new_cookie=1"
            return {"ec": 0}

        with unittest.mock.patch("moa.client.http_post_json", side_effect=fake_post):
            client = MoaClient("https://example.com/execute", "old_cookie=0")
            client.post({"method": "ping"})
        self.assertEqual(client.cookie, "new_cookie=1")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
