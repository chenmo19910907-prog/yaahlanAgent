#!/usr/bin/env python3
"""Admin MDP Nova client 鉴权失败自动刷新单测。"""

from __future__ import annotations

import json
import os
import sys
import unittest
import unittest.mock
from pathlib import Path

ADMIN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ADMIN_DIR))

from admin.client import (  # noqa: E402
    _is_mdp_business_auth_error,
    http_post_json,
)


class MdpNovaAuthRefreshTests(unittest.TestCase):
    def test_is_mdp_business_auth_error_ec_20000(self) -> None:
        self.assertTrue(_is_mdp_business_auth_error({"ec": 20000, "em": "请先登录"}))

    def test_http_post_json_retries_after_ec_20000(self) -> None:
        calls = {"count": 0}

        def fake_urlopen(req, timeout=0):
            calls["count"] += 1
            if calls["count"] == 1:
                body = json.dumps({"ec": 20000, "em": "请先登录"}).encode()

                class Resp:
                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        return False

                    def read(self):
                        return body

                return Resp()

            body = json.dumps({"ec": 200, "data": {"records": []}}).encode()

            class Resp:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def read(self):
                    return body

            return Resp()

        with unittest.mock.patch("admin.client.urllib.request.urlopen", side_effect=fake_urlopen), unittest.mock.patch(
            "admin.client._try_auto_refresh", return_value=True
        ), unittest.mock.patch.dict(
            os.environ,
            {
                "MDP_AEGIS_TOKEN": "refreshed_aegis",
                "MDP_CLOUD_AEGIS_TOKEN": "refreshed_cloud",
            },
            clear=False,
        ):
            result = http_post_json(
                "https://alpha-mdp-user-admin-api-stage.wemomo.com/userAdmin/queryUserProfileList",
                {"appId": 2005, "pageNo": 1, "pageSize": 1},
                auth="mdp_nova",
            )

        self.assertEqual(calls["count"], 2)
        self.assertEqual(result["ec"], 200)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
