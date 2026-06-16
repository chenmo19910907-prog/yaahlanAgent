"""Agent 读屏：Activity + UI 树 + 固定路径截图，供 Cursor 分析。"""

from __future__ import annotations

import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .activity import get_foreground_activity
from .device import display_size
from .screenshot import capture_live_png
from .ui_locator import dump_ui_xml

_MODULE_ROOT = Path(__file__).resolve().parent.parent
WATCH_DIR = _MODULE_ROOT / ".watch"
LIVE_SCREEN_PATH = WATCH_DIR / "live.png"
STATE_PATH = WATCH_DIR / "observe_state.json"

_DISPLAY_CACHE: dict[str, tuple[int, int, float]] = {}
_DISPLAY_CACHE_TTL_S = 120.0


def _ensure_dir() -> None:
    WATCH_DIR.mkdir(parents=True, exist_ok=True)


def _cached_display_size(serial: str) -> tuple[int, int]:
    now = time.time()
    hit = _DISPLAY_CACHE.get(serial)
    if hit and now - hit[2] < _DISPLAY_CACHE_TTL_S:
        return hit[0], hit[1]
    w, h = display_size(serial)
    _DISPLAY_CACHE[serial] = (w, h, now)
    return w, h


def _ui_hash(xml_text: str) -> str:
    return hashlib.sha256(xml_text.encode("utf-8")).hexdigest()[:16]


def _bounds_parts(bounds: str) -> tuple[int, int, int, int] | None:
    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not match:
        return None
    return tuple(map(int, match.groups()))  # type: ignore[return-value]


def _compact_ui_elements(
    xml_text: str,
    *,
    device_width: int,
    device_height: int,
    limit: int = 80,
    clickable_only: bool = False,
) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    items: list[dict[str, Any]] = []
    y_max = device_height - 60
    for node in root.iter():
        if len(items) >= limit * 2:
            break
        attrs = node.attrib
        clickable = attrs.get("clickable") == "true"
        text = (attrs.get("text") or "").strip()
        desc = (attrs.get("content-desc") or "").strip()
        rid = (attrs.get("resource-id") or "").strip()
        bounds = attrs.get("bounds") or ""
        if not bounds:
            continue
        if clickable_only and not clickable:
            continue
        if not (text or desc or rid) and not clickable:
            continue
        parts = _bounds_parts(bounds)
        if not parts:
            continue
        x1, y1, x2, y2 = parts
        if y2 < 80 or y1 > y_max:
            continue
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        label = text or desc or rid.split("/")[-1] or attrs.get("class", "")
        if not label and not clickable:
            continue
        items.append(
            {
                "label": label[:120],
                "text": text[:120],
                "accessibilityId": desc[:120],
                "resourceId": rid,
                "clickable": clickable,
                "bounds": bounds,
                "center": [cx, cy],
                "tapPct": [
                    round(cx / device_width, 4),
                    round(cy / device_height, 4),
                ],
            }
        )

    items.sort(key=lambda e: (e["center"][1], e["center"][0]))
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = f"{item['label']}|{item['bounds']}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def observe_screen(
    *,
    serial: str,
    include_image: bool = False,
    max_edge: int = 1170,
    ui_limit: int = 50,
    fast: bool = False,
) -> dict[str, Any]:
    """一次返回当前屏结构化信息；默认不截屏（原生页读 ui 树最快）。"""
    _ensure_dir()
    t0 = time.perf_counter()
    timing: dict[str, int] = {}

    if fast:
        include_image = False
        ui_limit = min(ui_limit, 45)

    dev_w, dev_h = _cached_display_size(serial)

    activity: dict[str, Any]
    xml_text: str
    screen: dict[str, Any] | None = None

    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="observe") as pool:
        t_parallel = time.perf_counter()
        fut_act = pool.submit(get_foreground_activity, serial=serial)
        fut_ui = pool.submit(dump_ui_xml, serial=serial)
        fut_img = (
            pool.submit(
                capture_live_png,
                serial=serial,
                dest=LIVE_SCREEN_PATH,
                max_edge=max_edge,
            )
            if include_image
            else None
        )
        activity = fut_act.result()
        timing["activityMs"] = int((time.perf_counter() - t_parallel) * 1000)
        xml_text = fut_ui.result()
        timing["uiDumpMs"] = int((time.perf_counter() - t_parallel) * 1000)
        if fut_img is not None:
            cap = fut_img.result()
            if cap.get("deviceWidth") and cap.get("deviceHeight"):
                dev_w = int(cap["deviceWidth"])
                dev_h = int(cap["deviceHeight"])
                _DISPLAY_CACHE[serial] = (dev_w, dev_h, time.time())
            screen = {
                "path": str(LIVE_SCREEN_PATH.resolve()),
                "width": cap.get("width"),
                "height": cap.get("height"),
                "deviceWidth": cap.get("deviceWidth", dev_w),
                "deviceHeight": cap.get("deviceHeight", dev_h),
                "scaleX": cap.get("scaleX", 1.0),
                "scaleY": cap.get("scaleY", 1.0),
                "maxEdge": max_edge,
            }
            timing["captureMs"] = int((time.perf_counter() - t_parallel) * 1000)

    t_parse = time.perf_counter()
    ui_hash = _ui_hash(xml_text)
    clickables = _compact_ui_elements(
        xml_text,
        device_width=dev_w,
        device_height=dev_h,
        limit=ui_limit,
        clickable_only=fast,
    )
    timing["parseMs"] = int((time.perf_counter() - t_parse) * 1000)
    timing["totalMs"] = int((time.perf_counter() - t0) * 1000)

    payload: dict[str, Any] = {
        "observedAt": time.time(),
        "serial": serial,
        "activity": activity,
        "uiHash": ui_hash,
        "ui": {
            "elementCount": len(clickables),
            "clickables": clickables,
        },
        "screen": screen,
        "timingMs": timing,
        "agentHint": (
            "原生页：默认无截图，直接读 ui.clickables；WebView/需看图时加 --image。"
            "操作后用 observe --wait（轮询仅 activity，结束后再 dump）。"
        ),
    }
    _save_state(payload)
    return payload


def _save_state(payload: dict[str, Any]) -> None:
    _ensure_dir()
    slim = {
        "observedAt": payload.get("observedAt"),
        "activity": (payload.get("activity") or {}).get("activity"),
        "uiHash": payload.get("uiHash"),
    }
    STATE_PATH.write_text(json.dumps(slim, ensure_ascii=False), encoding="utf-8")


def _load_state() -> dict[str, Any] | None:
    if not STATE_PATH.is_file():
        return None
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def wait_for_screen_change(
    *,
    serial: str,
    timeout_s: float = 12.0,
    poll_interval_s: float = 0.2,
    include_image: bool = False,
    max_edge: int = 1170,
    ui_limit: int = 50,
    fast: bool = False,
) -> dict[str, Any]:
    """等待 Activity/UI 变化；轮询阶段仅 dumpsys activity（快），命中后再完整 observe。"""
    baseline = _load_state()
    deadline = time.time() + max(0.5, timeout_s)
    last_activity = (baseline or {}).get("activity")
    last_hash = (baseline or {}).get("uiHash")
    polls = 0
    ui_check_every = 3

    while time.time() < deadline:
        polls += 1
        try:
            act = get_foreground_activity(serial=serial)
            cur_activity = act.get("activity") if act.get("ok") else None
            if last_activity and cur_activity and cur_activity != last_activity:
                out = observe_screen(
                    serial=serial,
                    include_image=include_image,
                    max_edge=max_edge,
                    ui_limit=ui_limit,
                    fast=fast,
                )
                out["wait"] = {
                    "changed": True,
                    "reason": "activity",
                    "timedOut": False,
                    "polls": polls,
                }
                return out

            if polls % ui_check_every == 0 and last_hash:
                cur_hash = _ui_hash(dump_ui_xml(serial=serial))
                if cur_hash != last_hash:
                    out = observe_screen(
                        serial=serial,
                        include_image=include_image,
                        max_edge=max_edge,
                        ui_limit=ui_limit,
                        fast=fast,
                    )
                    out["wait"] = {
                        "changed": True,
                        "reason": "ui",
                        "timedOut": False,
                        "polls": polls,
                    }
                    return out
        except Exception as exc:
            out = observe_screen(
                serial=serial,
                include_image=include_image,
                max_edge=max_edge,
                ui_limit=ui_limit,
                fast=fast,
            )
            out["wait"] = {
                "changed": False,
                "reason": "error",
                "error": str(exc),
                "timedOut": True,
                "polls": polls,
            }
            return out
        time.sleep(poll_interval_s)

    out = observe_screen(
        serial=serial,
        include_image=include_image,
        max_edge=max_edge,
        ui_limit=ui_limit,
        fast=fast,
    )
    out["wait"] = {"changed": False, "reason": "timeout", "timedOut": True, "polls": polls}
    return out
