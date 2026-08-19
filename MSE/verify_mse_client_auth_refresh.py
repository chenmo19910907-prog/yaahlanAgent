#!/usr/bin/env python3
"""MSE client 鉴权失败自动刷新单测。"""

from __future__ import annotations

import json
import os
import sys
import unittest
import unittest.mock
from pathlib import Path

MSE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MSE_DIR))

from mse.client import (  # noqa: E402
    _is_auth_body,
    _is_auth_error,
    get_configs_by_namespace,
)


class MseAuthRefreshTests(unittest.TestCase):
    def test_is_auth_body_detects_aegis_html(self) -> None:
        body = "<!doctype html><title>Aegis SSO_MSE管理平台</title>"
        self.assertTrue(_is_auth_body(body))

    def test_is_auth_error_http_401(self) -> None:
        self.assertTrue(_is_auth_error(401, "Unauthorized"))

    def test_get_configs_retries_after_auth_html(self) -> None:
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

            body = json.dumps({"ec": 0, "result": [{"configKey": "demo", "configValue": "{}"}]}).encode()

            class Resp:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def read(self):
                    return body

            return Resp()

        with unittest.mock.patch("mse.client.urllib.request.urlopen", side_effect=fake_urlopen), unittest.mock.patch(
            "mse.client._try_auto_refresh_mse", return_value=True
        ), unittest.mock.patch.dict(
            os.environ,
            {"MSE_COOKIE": "refreshed_cookie=1", "MOA_COOKIE": "refreshed_cookie=1"},
            clear=False,
        ):
            items = get_configs_by_namespace(
                base_url="https://mse.wemomo.com",
                cookie="old_cookie=0",
                region="alpha",
                app_key="demo.app",
                name_space="voga-common",
                cluster="stage",
                env="alpha",
                timeout_s=1.0,
            )

        self.assertEqual(calls["count"], 2)
        self.assertEqual(items[0]["configKey"], "demo")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
