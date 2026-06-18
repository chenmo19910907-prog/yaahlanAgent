"""E2E 原生设备驱动：launch / tap / key / text（不经 adb macro/chain）。"""

from __future__ import annotations

import os
import re
import subprocess
import time
from typing import Any

YAAHLAN_PACKAGE = "com.immomo.biz.yaahlan"
YAHA_PACKAGE = "com.immomo.yaha"
_DEFAULT_DISPLAY = (1080, 2340)

_APPS: dict[str, dict[str, Any]] = {
    "yaahlan": {
        "package": YAAHLAN_PACKAGE,
        "launch_mode": "launcher",
        "wait_ms": 4000,
        "force_stop": [YAAHLAN_PACKAGE, YAHA_PACKAGE],
    },
}


def _serial() -> str | None:
    serial = os.environ.get("E2E_DEVICE_SERIAL", "").strip()
    return serial or None


def _adb_cmd(*args: str, timeout_s: float = 60.0) -> subprocess.CompletedProcess[str]:
    cmd = ["adb"]
    serial = _serial()
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(args)
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"adb 超时: {' '.join(cmd)}") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 adb，请安装 platform-tools") from exc


def display_size(*, timeout_s: float = 2.0) -> tuple[int, int]:
    proc = _adb_cmd("shell", "wm", "size", timeout_s=timeout_s)
    match = re.search(r"(\d+)x(\d+)", proc.stdout + proc.stderr)
    if match:
        return int(match.group(1)), int(match.group(2))
    return _DEFAULT_DISPLAY


def launch_app(app_key: str = "yaahlan", *, wait_ms: int | None = None) -> dict[str, Any]:
    target = _APPS.get(app_key)
    if not target:
        raise ValueError(f"未知 app: {app_key}")

    pkg = str(target["package"])
    stopped: list[str] = []
    for stop_pkg in target.get("force_stop") or [pkg]:
        _adb_cmd("shell", "am", "force-stop", str(stop_pkg), timeout_s=10.0)
        stopped.append(str(stop_pkg))

    if target.get("launch_mode") == "launcher":
        proc = _adb_cmd(
            "shell",
            "monkey",
            "-p",
            pkg,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
            timeout_s=15.0,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "monkey 启动失败").strip())
        component = f"{pkg} (LAUNCHER)"
    else:
        raise ValueError(f"未实现 launch_mode: {target.get('launch_mode')}")

    delay_ms = int(wait_ms if wait_ms is not None else target.get("wait_ms") or 0)
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)

    return {
        "ok": True,
        "action": "launch",
        "app": app_key,
        "package": pkg,
        "component": component,
        "waitMs": delay_ms,
        "forceStopped": stopped,
    }


def tap_xy(x: int, y: int, *, timeout_s: float = 5.0) -> dict[str, Any]:
    proc = _adb_cmd("shell", "input", "tap", str(x), str(y), timeout_s=timeout_s)
    ok = proc.returncode == 0
    if not ok:
        raise RuntimeError((proc.stderr or proc.stdout or "tap 失败").strip())
    return {"ok": True, "action": "tap", "x": x, "y": y}


def tap_pct(tap_pct: list[float], *, timeout_s: float = 5.0) -> dict[str, Any]:
    w, h = display_size(timeout_s=min(timeout_s, 2.0))
    x = int(float(tap_pct[0]) * w)
    y = int(float(tap_pct[1]) * h)
    out = tap_xy(x, y, timeout_s=timeout_s)
    out["tapPct"] = tap_pct
    return out


def key_event(code: int, *, timeout_s: float = 5.0) -> dict[str, Any]:
    proc = _adb_cmd("shell", "input", "keyevent", str(code), timeout_s=timeout_s)
    ok = proc.returncode == 0
    if not ok:
        raise RuntimeError((proc.stderr or proc.stdout or "keyevent 失败").strip())
    return {"ok": True, "action": "key", "code": code}


def swipe(
    x1: int,
    y1: int,
    y2: int,
    *,
    x2: int | None = None,
    duration_ms: int = 300,
    timeout_s: float = 5.0,
) -> dict[str, Any]:
    x2_val = x1 if x2 is None else x2
    proc = _adb_cmd(
        "shell",
        "input",
        "swipe",
        str(x1),
        str(y1),
        str(x2_val),
        str(y2),
        str(duration_ms),
        timeout_s=timeout_s,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "swipe 失败").strip())
    return {"ok": True, "action": "swipe", "x1": x1, "y1": y1, "x2": x2_val, "y2": y2}


def clear_app_data(app_key: str = "yaahlan", *, timeout_s: float = 15.0) -> dict[str, Any]:
    target = _APPS.get(app_key)
    if not target:
        raise ValueError(f"未知 app: {app_key}")
    pkg = str(target["package"])
    proc = _adb_cmd("shell", "pm", "clear", pkg, timeout_s=timeout_s)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "pm clear 失败").strip())
    return {"ok": True, "action": "clear_app", "package": pkg}


def clear_input_field(*, max_chars: int = 12, timeout_s: float = 3.0) -> dict[str, Any]:
    key_event(123, timeout_s=timeout_s)  # MOVE_END
    deleted = 0
    for _ in range(max_chars):
        key_event(67, timeout_s=timeout_s)  # DEL
        deleted += 1
    return {"ok": True, "action": "clear_input", "deleted": deleted}


def input_text(text: str, *, timeout_s: float = 10.0, clear_first: bool = False) -> dict[str, Any]:
    if clear_first:
        clear_input_field(timeout_s=min(timeout_s, 5.0))
    safe = text.replace(" ", "%s")
    proc = _adb_cmd("shell", "input", "text", safe, timeout_s=timeout_s)
    ok = proc.returncode == 0
    if not ok:
        raise RuntimeError((proc.stderr or proc.stdout or "text 失败").strip())
    return {"ok": True, "action": "text", "text": text, "cleared": clear_first}
