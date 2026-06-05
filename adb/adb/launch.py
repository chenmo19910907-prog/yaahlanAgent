"""启动目标 App（供片段 launch_app 步骤与组合调用）。"""

from __future__ import annotations

import time
from typing import Any

from .apps import YAAHLAN, YAHA
from .device import run_adb


def launch_app(
    *,
    serial: str,
    app_key: str = "yaahlan",
) -> dict[str, Any]:
    if app_key not in ("yaahlan", "yaha"):
        raise ValueError(f"未知 app {app_key!r}，仅支持 yaahlan | yaha")
    target = YAAHLAN if app_key == "yaahlan" else YAHA
    pkg = str(target["package"])
    act = str(target["activity"])
    wait_ms = int(target["launch_wait_ms"])
    launch_mode = str(target.get("launch_mode", "activity"))

    # 冷启：先 force-stop 目标包（及易混用的 Yaha），再 LAUNCHER 启动
    force_stop: list[str] = [pkg]
    if app_key == "yaahlan":
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
        "app": app_key,
        "component": component,
        "waitMs": wait_ms,
    }
    if stopped:
        out["forceStopped"] = stopped
    return out
