"""截图采集与仅保留最新 N 张。"""

from __future__ import annotations

import platform
import shutil
import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .device import run_adb

_MODULE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCREENSHOT_DIR = _MODULE_ROOT / "screenshots"
DEFAULT_MAX_SCREENSHOTS = 2
DEFAULT_CAPTURE_MAX_EDGE = 1170


def screenshot_dir(custom: str | Path | None = None) -> Path:
    if custom is None:
        return DEFAULT_SCREENSHOT_DIR
    path = Path(custom)
    if not path.is_absolute():
        path = _MODULE_ROOT / path
    return path


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        header = f.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"不是有效 PNG: {path}")
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def image_point_to_device(
    x: int | float,
    y: int | float,
    *,
    image_width: int,
    image_height: int,
    device_width: int,
    device_height: int,
) -> tuple[int, int]:
    """读图坐标 → 设备 tap 坐标（按宽高各自线性缩放）。"""
    if image_width < 1 or image_height < 1:
        raise ValueError("image_width / image_height 须 >= 1")
    if device_width < 1 or device_height < 1:
        raise ValueError("device_width / device_height 须 >= 1")
    dx = int(round(float(x) * device_width / image_width))
    dy = int(round(float(y) * device_height / image_height))
    return dx, dy


def image_point_to_device_pct(
    x: int | float,
    y: int | float,
    *,
    image_width: int,
    image_height: int,
) -> tuple[float, float]:
    """读图坐标 → 设备比例坐标（0～1，与 tap_pct 一致）。"""
    if image_width < 1 or image_height < 1:
        raise ValueError("image_width / image_height 须 >= 1")
    return float(x) / image_width, float(y) / image_height


def coord_scale_from_capture(
    capture: Mapping[str, object],
) -> tuple[float, float, int, int]:
    """从 capture JSON 提取 (scaleX, scaleY, deviceWidth, deviceHeight)。"""
    device_w = int(capture.get("deviceWidth") or capture.get("width") or 0)
    device_h = int(capture.get("deviceHeight") or capture.get("height") or 0)
    image_w = int(capture.get("width") or device_w)
    image_h = int(capture.get("height") or device_h)
    if device_w < 1 or device_h < 1 or image_w < 1 or image_h < 1:
        raise ValueError("capture 缺少有效的 width/height/deviceWidth/deviceHeight")
    return device_w / image_w, device_h / image_h, device_w, device_h


def resolve_image_to_device(
    x: int | float,
    y: int | float,
    *,
    screenshot_path: Path,
    device_width: int,
    device_height: int,
) -> dict[str, object]:
    """读缩略图上的点，换算为设备像素与 tap_pct。"""
    image_w, image_h = png_dimensions(screenshot_path)
    device_x, device_y = image_point_to_device(
        x,
        y,
        image_width=image_w,
        image_height=image_h,
        device_width=device_width,
        device_height=device_height,
    )
    pct_x, pct_y = image_point_to_device_pct(
        x,
        y,
        image_width=image_w,
        image_height=image_h,
    )
    scale_x = device_width / image_w
    scale_y = device_height / image_h
    return {
        "imageX": int(round(float(x))),
        "imageY": int(round(float(y))),
        "imageWidth": image_w,
        "imageHeight": image_h,
        "deviceWidth": device_width,
        "deviceHeight": device_height,
        "scaleX": scale_x,
        "scaleY": scale_y,
        "deviceX": device_x,
        "deviceY": device_y,
        "tapPct": [pct_x, pct_y],
        "screenshot": str(screenshot_path.resolve()),
    }


def prune_screenshots(
    directory: Path,
    *,
    max_keep: int = DEFAULT_MAX_SCREENSHOTS,
    pattern: str = "screen_*.png",
) -> list[Path]:
    """删除旧截图，仅保留最新 max_keep 张（按修改时间）。"""
    if max_keep < 1:
        raise ValueError("max_keep 至少为 1")

    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime)
    removed: list[Path] = []
    while len(files) > max_keep:
        victim = files.pop(0)
        victim.unlink(missing_ok=True)
        removed.append(victim)
    return removed


def _resize_png_max_edge(path: Path, max_edge: int) -> None:
    """将 PNG 最长边缩至 max_edge（仅 macOS + sips，失败则保留原图）。"""
    if max_edge < 1:
        return
    if platform.system() != "Darwin" or not shutil.which("sips"):
        return
    subprocess.run(
        ["sips", "-Z", str(max_edge), str(path), "--out", str(path)],
        check=False,
        capture_output=True,
    )


def capture_screenshot(
    *,
    serial: str | None,
    directory: Path | None = None,
    max_keep: int = DEFAULT_MAX_SCREENSHOTS,
    max_edge: int | None = None,
) -> dict[str, object]:
    """截屏到本地目录，并 prune 为仅保留最新 max_keep 张。"""
    out_dir = directory or DEFAULT_SCREENSHOT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    path = out_dir / f"screen_{ts}.png"

    proc = run_adb(["exec-out", "screencap", "-p"], serial=serial, check=True)
    if not proc.stdout:
        raise RuntimeError("screencap 返回空数据")
    path.write_bytes(proc.stdout)

    device_width, device_height = png_dimensions(path)

    thumbnail = False
    if max_edge is not None:
        before_w, before_h = device_width, device_height
        _resize_png_max_edge(path, max_edge)
        after_w, after_h = png_dimensions(path)
        thumbnail = after_w != before_w or after_h != before_h

    width, height = png_dimensions(path)
    removed = prune_screenshots(out_dir, max_keep=max_keep)
    kept = sorted(out_dir.glob("screen_*.png"), key=lambda p: p.stat().st_mtime)

    scale_x = device_width / width if width else 1.0
    scale_y = device_height / height if height else 1.0

    payload: dict[str, object] = {
        "path": str(path.resolve()),
        "width": width,
        "height": height,
        "deviceWidth": device_width,
        "deviceHeight": device_height,
        "scaleX": scale_x,
        "scaleY": scale_y,
        "thumbnail": thumbnail,
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "removed": [str(p.resolve()) for p in removed],
        "kept": [str(p.resolve()) for p in kept],
        "maxKeep": max_keep,
    }
    if max_edge is not None:
        payload["maxEdge"] = max_edge
    if thumbnail:
        payload["coordHint"] = (
            f"读图像素 (x,y) → 设备 tap: x*scaleX, y*scaleY "
            f"(scaleX={scale_x:.4f}, scaleY={scale_y:.4f})"
        )
    return payload


def latest_screenshot(directory: Path | None = None) -> Path | None:
    out_dir = directory or DEFAULT_SCREENSHOT_DIR
    if not out_dir.is_dir():
        return None
    files = sorted(out_dir.glob("screen_*.png"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None
