"""基于坐标的屏幕操作。"""

from __future__ import annotations

from .device import run_adb


def tap(*, x: int, y: int, serial: str | None) -> None:
    if x < 0 or y < 0:
        raise ValueError(f"坐标不能为负: ({x}, {y})")
    run_adb(["shell", "input", "tap", str(x), str(y)], serial=serial, check=True)


def swipe(
    *,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration_ms: int,
    serial: str | None,
) -> None:
    if duration_ms < 0:
        raise ValueError("duration_ms 不能为负")
    run_adb(
        [
            "shell",
            "input",
            "swipe",
            str(x1),
            str(y1),
            str(x2),
            str(y2),
            str(duration_ms),
        ],
        serial=serial,
        check=True,
    )


def keyevent(*, code: int, serial: str | None) -> None:
    run_adb(["shell", "input", "keyevent", str(code)], serial=serial, check=True)


def clear_input_field(*, serial: str | None, max_chars: int = 64) -> None:
    """清空当前焦点输入框：移到末尾再连续退格。"""
    if max_chars < 1:
        raise ValueError("max_chars 须 >= 1")
    keyevent(code=123, serial=serial)  # KEYCODE_MOVE_END
    for _ in range(max_chars):
        keyevent(code=67, serial=serial)  # KEYCODE_DEL


def input_text(*, text: str, serial: str | None, clear_first: bool = True) -> None:
    """发送文本（空格等需按 adb input 规则转义）。默认先清空焦点输入框。"""
    if clear_first:
        clear_input_field(serial=serial)
    escaped = text.replace(" ", "%s")
    run_adb(["shell", "input", "text", escaped], serial=serial, check=True)
