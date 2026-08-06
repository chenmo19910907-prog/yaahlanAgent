"""本仓库 ADB 自动化目标 App（勿混用包名）。"""

from __future__ import annotations

from typing import TypedDict

from .project_paths import get_project_id


class AppTarget(TypedDict, total=False):
    label: str
    package: str
    activity: str
    launch_wait_ms: int
    launch_mode: str  # "activity" | "launcher"
    splash_ad_max_ms: int
    splash_ad_script_id: str


# Firebase / 截图文件名中的正式包名均为 com.immomo.biz.yaahlan
YAAHLAN: AppTarget = {
    "label": "Yaahlan",
    "package": "com.immomo.biz.yaahlan",
    "activity": ".personalityIcon4",
    "launch_mode": "launcher",
    "launch_wait_ms": 4000,
    "splash_ad_max_ms": 8000,
    "splash_ad_script_id": "dismiss-splash-ad",
}

# 桌面图标常为「Yaha」，与 Yaahlan 为不同产品
YAHA: AppTarget = {
    "label": "Yaha",
    "package": "com.immomo.yaha",
    "activity": "com.immomo.app_boot.NormalFlutterActivity",
    "launch_wait_ms": 4000,
}


def _app_target_from_project() -> AppTarget:
    try:
        from project.loader import (
            app_android_activity,
            app_android_launch_mode,
            app_android_launch_wait_ms,
            app_android_package,
            app_android_splash_ad_max_ms,
            app_android_splash_ad_script_id,
            get_project_config,
        )

        cfg = get_project_config()
        display = str(cfg.get("displayName") or get_project_id()).strip()
        return AppTarget(
            label=display or "App",
            package=app_android_package(),
            activity=app_android_activity(),
            launch_mode=app_android_launch_mode(),
            launch_wait_ms=app_android_launch_wait_ms(),
            splash_ad_max_ms=app_android_splash_ad_max_ms(),
            splash_ad_script_id=app_android_splash_ad_script_id(),
        )
    except (ImportError, FileNotFoundError, ValueError, OSError):
        return YAAHLAN


def resolve_app_target(app_key: str | None = None) -> AppTarget:
    """按 app_key 或当前 AGENT_PROJECT 解析启动目标。"""
    key = str(app_key or "").strip().lower()
    pid = get_project_id().lower()
    if not key or key in (pid, "default", "app", "project"):
        return _app_target_from_project()
    if key == "yaahlan":
        return YAAHLAN
    if key == "yaha":
        return YAHA
    if key == "example":
        return _app_target_from_project()
    raise ValueError(f"未知 app {app_key!r}，支持: yaahlan | yaha | {get_project_id()} | default")


DEFAULT_APP = YAAHLAN
