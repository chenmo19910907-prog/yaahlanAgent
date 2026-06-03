"""截图采集与仅保留最新 N 张。"""

from __future__ import annotations

import struct
from datetime import datetime, timezone
from pathlib import Path

from .device import run_adb

_MODULE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCREENSHOT_DIR = _MODULE_ROOT / "screenshots"
DEFAULT_MAX_SCREENSHOTS = 2


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


def capture_screenshot(
    *,
    serial: str | None,
    directory: Path | None = None,
    max_keep: int = DEFAULT_MAX_SCREENSHOTS,
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

    width, height = png_dimensions(path)
    removed = prune_screenshots(out_dir, max_keep=max_keep)
    kept = sorted(out_dir.glob("screen_*.png"), key=lambda p: p.stat().st_mtime)

    return {
        "path": str(path.resolve()),
        "width": width,
        "height": height,
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "removed": [str(p.resolve()) for p in removed],
        "kept": [str(p.resolve()) for p in kept],
        "maxKeep": max_keep,
    }


def latest_screenshot(directory: Path | None = None) -> Path | None:
    out_dir = directory or DEFAULT_SCREENSHOT_DIR
    if not out_dir.is_dir():
        return None
    files = sorted(out_dir.glob("screen_*.png"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None
