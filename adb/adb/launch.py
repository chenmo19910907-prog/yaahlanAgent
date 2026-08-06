"""启动目标 App（供片段 launch_app 步骤与组合调用）。"""

from __future__ import annotations

import time
from typing import Any

from .apps import YAHA, resolve_app_target
from .device import run_adb
from .project_paths import get_project_id


def launch_app(
    *,
    serial: str,
    app_key: str | None = None,
) -> dict[str, Any]:
    key = str(app_key or get_project_id()).strip().lower()
    target = resolve_app_target(key)
    pkg = str(target["package"])
    act = str(target.get("activity") or "")
    wait_ms = int(target.get("launch_wait_ms") or 4000)
    launch_mode = str(target.get("launch_mode") or "activity")

    force_stop: list[str] = [pkg]
    if key == "yaahlan" or pkg == YAAHLAN["package"]:
        yaha_pkg = str(YAHA["package"])
        if yaha_pkg not in force_stop:
            force_stop.append(yaha_pkg)

    stopped: list[str] = []
    for stop_pkg in force_stop:
        run_adb(["shell", "am", "force-stop", stop_pkg], serial=serial, check=True)
        stopped.append(stop_pkg)

    if launch_mode == "launcher":
        run_adb(
            [
                "shell",
                "monkey",
                "-p",
                pkg,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
            serial=serial,
            check=True,
        )
        component = f"{pkg} (LAUNCHER)"
    else:
        component = f"{pkg}/{act.lstrip('/')}"
        run_adb(["shell", "am", "start", "-n", component], serial=serial, check=True)

    if wait_ms > 0:
        time.sleep(wait_ms / 1000.0)

    out: dict[str, Any] = {
        "action": "launch_app",
        "app": key,
        "component": component,
        "waitMs": wait_ms,
    }
    if stopped:
        out["forceStopped"] = stopped
    return out
