#!/usr/bin/env python3
"""验证 MSE 配置分享链接生成。"""

from __future__ import annotations

import sys
from pathlib import Path

MSE_DIR = Path(__file__).resolve().parent
if str(MSE_DIR) not in sys.path:
    sys.path.insert(0, str(MSE_DIR))

from mse.share_link import build_mse_config_share_link, resolve_share_link_params  # noqa: E402


def main() -> int:
    expected = (
        "https://mse.wemomo.com/#/config/app?"
        "corp=alpha&env=stage&appKey=momo.ibt.yaahlan.service.yaahlan-trick"
        "&nameSpace=Application&configKey=cpLoveChestConfigAreaMap"
    )
    link = build_mse_config_share_link("cpLoveChestConfigAreaMap")
    assert link == expected, link

    params = resolve_share_link_params("familyPkConfig")
    assert params["app_key"] == "momo.bpm.biz.gameplatform.overseas-voga-mts-vas"
    assert params["name_space"] == "voga-common"

    custom = build_mse_config_share_link(
        "demoConfig",
        app_key="demo.app",
        name_space="Application",
    )
    assert "appKey=demo.app" in custom
    assert "configKey=demoConfig" in custom

    print("verify_mse_share_link: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
