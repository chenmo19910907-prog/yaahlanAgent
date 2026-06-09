"""房间面板 Close the room 开关：按圆钮白/灰读图判态（勿信 uiautomator checked）。"""

from __future__ import annotations

import re
import struct
import time
import zlib
from pathlib import Path
from typing import Any, Literal

from .actions import tap
from .screenshot import capture_screenshot, latest_screenshot
from .ui_locator import dump_ui_xml, find_by_resource_id

CLOSE_SWITCH_RESOURCE_ID = "close_switch_btn"
ROOM_PANEL_OPEN_RESOURCE_ID = "iv_room_close"
# 圆钮亮度：OFF≈80、ON≈255；取中间阈值
KNOB_ON_MIN_LUMINANCE = 150.0
# 裁切开关区域时避开右下角 Dev 角标
CROP_WIDTH_FRAC = 0.78
CROP_HEIGHT_FRAC = 0.72


def _parse_bounds(bounds: str) -> tuple[int, int, int, int] | None:
    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not match:
        return None
    return tuple(map(int, match.groups()))  # type: ignore[return-value]


def _read_png_rgb(path: Path) -> tuple[int, int, list[tuple[int, int, int]]]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"不是有效 PNG: {path}")

    pos = 8
    width = height = 0
    color_type: int | None = None
    idat = b""
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        ctype = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            width, height, _bit_depth, color_type = struct.unpack(">IIBBBBB", chunk[:13])[:4]
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break

    if color_type not in (2, 6):
        raise ValueError(f"仅支持 RGB/RGBA PNG: {path}")

    raw = zlib.decompress(idat)
    bpp = 3 if color_type == 2 else 4
    stride = width * bpp
    rows: list[bytearray] = []
    i = 0
    for _y in range(height):
        filt = raw[i]
        i += 1
        row = bytearray(raw[i : i + stride])
        i += stride
        if filt == 1:
            for x in range(bpp, stride):
                row[x] = (row[x] + row[x - bpp]) & 255
        elif filt == 2 and rows:
            prev = rows[-1]
            for x in range(stride):
                row[x] = (row[x] + prev[x]) & 255
        elif filt == 3:
            if rows:
                prev = rows[-1]
                for x in range(stride):
                    left = row[x - bpp] if x >= bpp else 0
                    row[x] = (row[x] + (left + prev[x]) // 2) & 255
            else:
                for x in range(bpp, stride):
                    row[x] = (row[x] + row[x - bpp] // 2) & 255
        elif filt == 4 and rows:
            prev = rows[-1]
            for x in range(stride):
                left = row[x - bpp] if x >= bpp else 0
                up = prev[x]
                up_left = prev[x - bpp] if x >= bpp else 0
                p = left + up - up_left
                pa = abs(p - left)
                pb = abs(p - up)
                pc = abs(p - up_left)
                pr = left if pa <= pb and pa <= pc else (up if pb <= pc else up_left)
                row[x] = (row[x] + pr) & 255
        elif filt == 4:
            for x in range(bpp, stride):
                row[x] = (row[x] + row[x - bpp]) & 255
        rows.append(row)

    pixels: list[tuple[int, int, int]] = []
    for row in rows:
        for x in range(width):
            if color_type == 2:
                pixels.append(tuple(row[x * 3 : (x + 1) * 3]))
            else:
                r, g, b, _a = row[x * 4 : (x + 1) * 4]
                pixels.append((r, g, b))
    return width, height, pixels


def _luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


def _knob_stats_from_bounds(
    *,
    screenshot_path: Path,
    bounds: tuple[int, int, int, int],
    scale_x: float,
    scale_y: float,
) -> dict[str, Any]:
    img_w, img_h, pixels = _read_png_rgb(screenshot_path)
    x1, y1, x2, y2 = bounds
    ix1 = int(round(x1 / scale_x))
    iy1 = int(round(y1 / scale_y))
    ix2 = int(round(x2 / scale_x))
    iy2 = int(round(y2 / scale_y))

    crop_w = max(1, int((ix2 - ix1) * CROP_WIDTH_FRAC))
    crop_h = max(1, int((iy2 - iy1) * CROP_HEIGHT_FRAC))
    crop: list[tuple[int, int, int]] = []
    for cy in range(crop_h):
        for cx in range(crop_w):
            img_x = max(0, min(img_w - 1, ix1 + cx))
            img_y = max(0, min(img_h - 1, iy1 + cy))
            crop.append(pixels[img_y * img_w + img_x])

    ranked = sorted(((_luminance(px), px) for px in crop), reverse=True)
    top_n = max(5, int(len(crop) * 0.05))
    top = ranked[:top_n]
    avg = tuple(sum(px[i] for _lum, px in top) / len(top) for i in range(3))
    avg_lum = _luminance(avg)  # type: ignore[arg-type]
    peak_lum, peak_rgb = ranked[0]

    if avg_lum >= KNOB_ON_MIN_LUMINANCE:
        state: Literal["on", "off", "uncertain"] = "on"
        knob_color = "white"
    elif avg_lum < KNOB_ON_MIN_LUMINANCE:
        state = "off"
        knob_color = "gray"
    else:
        state = "uncertain"
        knob_color = "unknown"

    return {
        "state": state,
        "knobColor": knob_color,
        "knobLuminance": round(avg_lum, 1),
        "knobRgb": [round(c) for c in avg],
        "peakLuminance": round(peak_lum, 1),
        "peakRgb": list(peak_rgb),
        "bounds": list(bounds),
        "cropImageRect": [ix1, iy1, ix1 + crop_w, iy1 + crop_h],
        "imageSize": [img_w, img_h],
        "scale": [scale_x, scale_y],
    }


def find_close_switch_in_xml(xml_text: str) -> dict[str, Any] | None:
    hit = find_by_resource_id(xml_text, CLOSE_SWITCH_RESOURCE_ID)
    if not hit:
        return None
    parsed = _parse_bounds(str(hit.get("bounds") or ""))
    if not parsed:
        return None
    x1, y1, x2, y2 = parsed
    tap_x = x1 + int((x2 - x1) * 0.55)
    tap_y = (y1 + y2) // 2
    return {
        **hit,
        "boundsTuple": parsed,
        "tapX": tap_x,
        "tapY": tap_y,
        "checkedAttr": None,
    }


def _checked_from_xml(xml_text: str) -> str | None:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_text)
    for node in root.iter():
        rid = str(node.attrib.get("resource-id") or "")
        if rid.endswith(f"/{CLOSE_SWITCH_RESOURCE_ID}") or rid.endswith(CLOSE_SWITCH_RESOURCE_ID):
            return node.attrib.get("checked")
    return None


def open_room_panel_if_needed(*, serial: str) -> dict[str, Any]:
    """若未见 close_switch，点 iv_room_close 打开面板。"""
    xml_text = dump_ui_xml(serial=serial)
    if find_close_switch_in_xml(xml_text):
        return {"panelOpen": True, "openedNow": False}

    opener = find_by_resource_id(xml_text, ROOM_PANEL_OPEN_RESOURCE_ID)
    if not opener:
        raise RuntimeError("未找到 iv_room_close，无法打开房间功能面板")
    tap(x=int(opener["x"]), y=int(opener["y"]), serial=serial)
    time.sleep(1.0)
    xml_after = dump_ui_xml(serial=serial)
    if not find_close_switch_in_xml(xml_after):
        raise RuntimeError("点击 iv_room_close 后仍未见 close_switch_btn")
    return {"panelOpen": True, "openedNow": True, "tap": [opener["x"], opener["y"]]}


def detect_close_switch_state(
    *,
    serial: str,
    screenshot_path: Path | None = None,
    bounds: tuple[int, int, int, int] | None = None,
) -> dict[str, Any]:
    """capture 读图判态：圆钮白=on，灰=off。"""
    capture = capture_screenshot(serial=serial)
    path = screenshot_path or Path(str(capture["path"]))
    scale_x = float(capture.get("scaleX") or 1.0)
    scale_y = float(capture.get("scaleY") or 1.0)

    xml_text = dump_ui_xml(serial=serial)
    switch = find_close_switch_in_xml(xml_text)
    if not switch and bounds is None:
        raise RuntimeError("当前未见 close_switch_btn，请先打开房间功能面板")

    use_bounds = bounds or switch["boundsTuple"]  # type: ignore[index]
    checked_attr = _checked_from_xml(xml_text)
    stats = _knob_stats_from_bounds(
        screenshot_path=path,
        bounds=use_bounds,
        scale_x=scale_x,
        scale_y=scale_y,
    )

    checked_bool: bool | None = None
    if checked_attr in ("true", "false"):
        checked_bool = checked_attr == "true"

    vision_on = stats["state"] == "on"
    mismatch = checked_bool is not None and checked_bool != vision_on

    return {
        "ok": stats["state"] != "uncertain",
        "closeRoomSwitch": stats["state"],
        "knobColor": stats["knobColor"],
        "knobLuminance": stats["knobLuminance"],
        "knobRgb": stats["knobRgb"],
        "peakLuminance": stats["peakLuminance"],
        "checkedAttr": checked_attr,
        "checkedMismatch": mismatch,
        "hint": (
            "圆钮偏白(亮度≥150)=ON；偏灰(<150)=OFF。"
            "勿单独信 uiautomator checked。"
        ),
        "bounds": stats["bounds"],
        "screenshot": str(path.resolve()),
        "capture": capture,
        "locator": switch,
        **{k: stats[k] for k in ("cropImageRect", "imageSize", "scale")},
    }


def ensure_close_switch_state(
    *,
    serial: str,
    desired: Literal["on", "off"],
    max_attempts: int = 3,
) -> dict[str, Any]:
    """打开面板后读图，必要时点击开关直至达到目标态。"""
    panel = open_room_panel_if_needed(serial=serial)
    attempts: list[dict[str, Any]] = []

    for i in range(max_attempts):
        probe = detect_close_switch_state(serial=serial)
        attempts.append(
            {
                "attempt": i + 1,
                "state": probe["closeRoomSwitch"],
                "knobLuminance": probe["knobLuminance"],
                "checkedAttr": probe.get("checkedAttr"),
            }
        )
        if probe["closeRoomSwitch"] == desired:
            return {
                "ok": True,
                "desired": desired,
                "final": probe,
                "panel": panel,
                "attempts": attempts,
            }
        if probe["closeRoomSwitch"] == "uncertain":
            raise RuntimeError(f"第 {i + 1} 次读图无法判定开关态: {probe}")

        locator = probe.get("locator") or {}
        tap_x = int(locator.get("tapX") or locator.get("x") or 0)
        tap_y = int(locator.get("tapY") or locator.get("y") or 0)
        if tap_x < 1 or tap_y < 1:
            raise RuntimeError("缺少 close_switch_btn 点击坐标")
        tap(x=tap_x, y=tap_y, serial=serial)
        time.sleep(0.9)

    final = detect_close_switch_state(serial=serial)
    return {
        "ok": final["closeRoomSwitch"] == desired,
        "desired": desired,
        "final": final,
        "panel": panel,
        "attempts": attempts,
        "error": f"已达最大尝试次数 {max_attempts}，当前为 {final['closeRoomSwitch']}",
    }
