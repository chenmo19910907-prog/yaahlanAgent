"""连续操作链：确定路径可一次截图后多点，仅在边界再截图。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Literal

from .actions import input_text, keyevent, swipe, tap
from .coords import pct_to_pixel
from .device import AdbError, display_size
from .device_profile import (
    adapt_steps,
    adaptation_payload,
    resolve_adaptation,
)
from .screenshot import capture_screenshot

CaptureMode = Literal["never", "start", "end", "both"]

_STEP_TYPES = frozenset(
    {"sleep", "tap", "tap_pct", "swipe", "key", "text", "capture", "launch_app", "run_script"}
)


def _resolve_tap(
    step: dict[str, Any],
    *,
    width: int,
    height: int,
) -> tuple[int, int]:
    if "tap" in step:
        xy = step["tap"]
        if not isinstance(xy, (list, tuple)) or len(xy) != 2:
            raise ValueError(f"tap 须为 [x, y]: {step}")
        return int(xy[0]), int(xy[1])
    if "tap_pct" in step:
        pct = step["tap_pct"]
        if not isinstance(pct, (list, tuple)) or len(pct) != 2:
            raise ValueError(f"tap_pct 须为 [x, y] 比例 0~1: {step}")
        return pct_to_pixel(width, height, float(pct[0]), float(pct[1]))
    raise ValueError(f"步骤缺少 tap 或 tap_pct: {step}")


def run_chain(
    *,
    serial: str,
    steps: list[dict[str, Any]],
    capture: CaptureMode = "end",
    screenshot_dir: Path,
    max_screenshots: int,
    use_adaptation: bool = True,
    text: str | None = None,
    skip: set[str] | None = None,
) -> dict[str, Any]:
    if not steps:
        raise ValueError("steps 不能为空")

    adapt_ctx = resolve_adaptation(serial) if use_adaptation else None
    if adapt_ctx and adapt_ctx.status == "uncalibrated":
        raise AdbError(adapt_ctx.message)
    if adapt_ctx:
        steps = adapt_steps(steps, adapt_ctx)

    from .macros import apply_skip_flags

    steps = apply_skip_flags(steps, skip=skip or set())

    width, height = display_size(serial)
    executed: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "serial": serial,
        "displayWidth": width,
        "displayHeight": height,
        "capture": capture,
        "stepsExecuted": executed,
    }
    if adapt_ctx:
        result["adaptation"] = adaptation_payload(adapt_ctx)

    def _do_capture(label: str) -> dict[str, Any]:
        cap = capture_screenshot(
            serial=serial,
            directory=screenshot_dir,
            max_keep=max_screenshots,
        )
        cap["capturePoint"] = label
        result["screenshot"] = cap
        return cap

    if capture in ("start", "both"):
        _do_capture("start")

    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"步骤 {index} 须为 object")
        kind = step.get("type")
        if kind is None:
            if "run_script" in step:
                kind = "run_script"
            elif "launch_app" in step:
                kind = "launch_app"
            elif "sleep" in step or "sleep_ms" in step:
                kind = "sleep"
            elif "tap" in step or "tap_pct" in step:
                kind = "tap"
            elif "swipe" in step:
                kind = "swipe"
            elif "key" in step:
                kind = "key"
            elif "text" in step:
                kind = "text"
            elif step.get("capture"):
                kind = "capture"
            else:
                raise ValueError(f"步骤 {index} 无法识别: {step}")
        if kind not in _STEP_TYPES:
            raise ValueError(f"未知步骤类型 {kind!r}，支持: {sorted(_STEP_TYPES)}")

        entry: dict[str, Any] = {"index": index, "type": kind}
        if step.get("note"):
            entry["note"] = step["note"]
        if step.get("optional"):
            entry["optional"] = True

        if kind == "sleep":
            ms = int(step.get("sleep_ms", step.get("sleep", 0)))
            if ms > 0:
                time.sleep(ms / 1000.0)
            entry["sleepMs"] = ms
        elif kind == "tap":
            x, y = _resolve_tap(step, width=width, height=height)
            tap(x=x, y=y, serial=serial)
            entry["x"] = x
            entry["y"] = y
            if step.get("tap_pct_ref"):
                entry["tapPctRef"] = step["tap_pct_ref"]
                entry["tapPct"] = step.get("tap_pct")
        elif kind == "swipe":
            sw = step["swipe"]
            if not isinstance(sw, dict):
                raise ValueError(f"swipe 须为 object: {step}")
            swipe(
                x1=int(sw["x1"]),
                y1=int(sw["y1"]),
                x2=int(sw["x2"]),
                y2=int(sw["y2"]),
                duration_ms=int(sw.get("duration_ms", 300)),
                serial=serial,
            )
            entry["swipe"] = sw
        elif kind == "key":
            code = int(step["key"])
            keyevent(code=code, serial=serial)
            entry["key"] = code
        elif kind == "text":
            content = str(step["text"])
            if not content:
                raise ValueError(f"text 不能为空: {step}")
            input_text(text=content, serial=serial)
            entry["text"] = content
        elif kind == "capture":
            cap = _do_capture(f"step_{index}")
            entry["screenshot"] = cap["path"]
        elif kind == "launch_app":
            from .launch import launch_app as do_launch

            app_key = str(step.get("launch_app", "yaahlan"))
            launch_info = do_launch(serial=serial, app_key=app_key)
            entry["launchApp"] = app_key
            entry["launch"] = launch_info
        elif kind == "run_script":
            from .recorded_scripts import load_fragment

            script_key = str(step["run_script"])
            block_skip = set(step.get("skip") or []) | (skip or set())
            frag = load_fragment(script_key, text=text)
            nested = apply_skip_flags(list(frag.get("steps", [])), skip=block_skip)
            sub = run_chain(
                serial=serial,
                steps=nested,
                capture="never",
                screenshot_dir=screenshot_dir,
                max_screenshots=max_screenshots,
                use_adaptation=use_adaptation,
                text=text,
                skip=block_skip,
            )
            entry["runScript"] = frag.get("name", script_key)
            entry["scriptId"] = frag.get("id", script_key)
            entry["nestedSteps"] = sub.get("stepsExecuted")

        executed.append(entry)

    if capture in ("end", "both") and "screenshot" not in result:
        _do_capture("end")
    elif capture == "never":
        result["screenshot"] = None

    return result


def load_steps_file(path: Path) -> tuple[list[dict[str, Any]], CaptureMode]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("步骤文件根节点须为 object")
    capture = data.get("capture", "end")
    if capture not in ("never", "start", "end", "both"):
        raise ValueError(f"capture 无效: {capture}")
    steps = data.get("steps")
    if not isinstance(steps, list):
        raise ValueError("steps 须为数组")
    return steps, capture
