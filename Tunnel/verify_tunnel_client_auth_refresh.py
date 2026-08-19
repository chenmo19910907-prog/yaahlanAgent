#!/usr/bin/env python3
"""Tunnel client 鉴权失败自动刷新单测。"""

from __future__ import annotations

import json
import os
import sys
import unittest
import unittest.mock
from pathlib import Path

TUNNEL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TUNNEL_DIR))

from tunnel.client import (  # noqa: E402
    _is_auth_body,
    _is_auth_error,
    _is_tunnel_business_auth_error,
    http_get_json,
)


class TunnelAuthRefreshTests(unittest.TestCase):
    def test_is_auth_body_detects_aegis_html(self) -> None:
        body = "<!doctype html><title>Aegis SSO_MSE管理平台</title>"
        self.assertTrue(_is_auth_body(body))

    def test_is_auth_error_http_401(self) -> None:
        self.assertTrue(_is_auth_error(401, "Unauthorized"))

    def test_is_tunnel_business_auth_error(self) -> None:
        self.assertTrue(_is_tunnel_business_auth_error({"ec": 401, "em": "请先登录"}))

    def test_http_get_json_retries_after_auth_html(self) -> None:
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
                    return json.dumps({"ec": 200, "em": "success", "data": {"list": []}}).encode()

            return Resp()

        with unittest.mock.patch("tunnel.client.urllib.request.urlopen", side_effect=fake_urlopen), unittest.mock.patch(
            "tunnel.client._try_auto_refresh_tunnel", return_value=True
        ), unittest.mock.patch.dict(
            os.environ,
            {"TUNNEL_COOKIE": "refreshed_cookie=1", "MOA_COOKIE": "refreshed_cookie=1"},
            clear=False,
        ):
            result = http_get_json("https://tunnel.wemomo.com/api/requests?momoid=1&start_time=1", timeout_s=1.0)

        self.assertEqual(calls["count"], 2)
        self.assertEqual(result["ec"], 200)

    def test_http_get_json_retries_after_ec_401(self) -> None:
        calls = {"count": 0}

        def fake_urlopen(req, timeout=0):
            calls["count"] += 1
            if calls["count"] == 1:
                body = json.dumps({"ec": 401, "em": "请先登录"}).encode()

                class Resp:
                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        return False

                    def read(self):
                        return body

                return Resp()

            body = json.dumps({"ec": 200, "em": "success", "data": {"list": []}}).encode()

            class Resp:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def read(self):
                    return body

            return Resp()

        with unittest.mock.patch("tunnel.client.urllib.request.urlopen", side_effect=fake_urlopen), unittest.mock.patch(
            "tunnel.client._try_auto_refresh_tunnel", return_value=True
        ), unittest.mock.patch.dict(
            os.environ,
            {"TUNNEL_COOKIE": "refreshed_cookie=1"},
            clear=False,
        ):
            result = http_get_json("https://tunnel.wemomo.com/api/requests?momoid=1&start_time=1", timeout_s=1.0)

        self.assertEqual(calls["count"], 2)
        self.assertEqual(result["ec"], 200)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
