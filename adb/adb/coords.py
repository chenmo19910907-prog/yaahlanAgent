"""屏幕坐标：绝对像素与相对比例互转。"""

from __future__ import annotations


def pct_to_pixel(
    width: int,
    height: int,
    x_pct: float,
    y_pct: float,
) -> tuple[int, int]:
    if not (0.0 <= x_pct <= 1.0 and 0.0 <= y_pct <= 1.0):
        raise ValueError(f"比例须在 0~1 之间: ({x_pct}, {y_pct})")
    return int(width * x_pct), int(height * y_pct)


def pixel_to_pct(
    width: int,
    height: int,
    x: int,
    y: int,
) -> tuple[float, float]:
    if width <= 0 or height <= 0:
        raise ValueError(f"无效屏幕尺寸: {width}x{height}")
    return x / width, y / height
