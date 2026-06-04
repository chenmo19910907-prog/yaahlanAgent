"""本仓库 ADB 自动化目标 App（勿混用包名）。"""

from __future__ import annotations

from typing import TypedDict


class AppTarget(TypedDict, total=False):
    label: str
    package: str
    activity: str
    launch_wait_ms: int
    launch_mode: str  # "activity" | "launcher"


# Firebase / 截图文件名中的正式包名均为 com.immomo.biz.yaahlan
YAAHLAN: AppTarget = {
    "label": "Yaahlan",
    "package": "com.immomo.biz.yaahlan",
    "activity": ".personalityIcon4",
    "launch_mode": "launcher",
    "launch_wait_ms": 6000,
}

# 桌面图标常为「Yaha」，与 Yaahlan 为不同产品
YAHA: AppTarget = {
    "label": "Yaha",
    "package": "com.immomo.yaha",
    "activity": "com.immomo.app_boot.NormalFlutterActivity",
    "launch_wait_ms": 4000,
}

DEFAULT_APP = YAAHLAN
