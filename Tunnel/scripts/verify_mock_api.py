#!/usr/bin/env python3
"""Tunnel Mock API 冒烟（只读 list；不创建/删除）。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tunnel.env import load_local_env
from tunnel.mock_api import list_mock_cases, list_param_mocks, normalize_uri
from tunnel.paths import tunnel_dir

URI = "http://gw-api-alpha.yaahlan.fun/yaahlan/trick/cpLoveChest/getCpLoveChestHomepage"
MOMOID = "100414599"


def main() -> int:
    load_local_env(tunnel_dir())
    uri = normalize_uri(URI)
    cases = list_mock_cases(uri=uri, momoid=MOMOID)
    params = list_param_mocks(uri=uri, momoid=MOMOID)
    assert isinstance(cases, list)
    assert isinstance(params, list)
    print(f"ok uri={uri} cases={len(cases)} params={len(params)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
