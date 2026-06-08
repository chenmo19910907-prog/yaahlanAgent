"""App 语言 RTL：原生页水平镜像 tap/swipe（x' = 1 − x）。"""

from __future__ import annotations

from typing import Any, Literal

RtlMode = Literal["off", "on"]

# WebView / Flutter 等勿盲目镜像（见 adb/README.md）
_NO_MIRROR_HINTS = frozenset({"webview", "flutter"})


def mirror_x_pct(x_pct: float) -> float:
    return 1.0 - float(x_pct)


def mirror_x_pixel(x: int, *, width: int) -> int:
    return int(width) - int(x)


def step_mirror_override(step: dict[str, Any]) -> bool | None:
    if "rtl_mirror" not in step:
        return None
    return bool(step["rtl_mirror"])


def _is_bottom_bar_step(step: dict[str, Any]) -> bool:
    pct = step.get("tap_pct")
    if isinstance(pct, (list, tuple)) and len(pct) >= 2:
        try:
            return float(pct[1]) >= 0.9
        except (TypeError, ValueError):
            pass
    note = str(step.get("note", "")).lower()
    return "底栏" in note or "tab_" in note


def _is_native_me_chrome_step(step: dict[str, Any]) -> bool:
    note = str(step.get("note", "")).lower()
    return any(k in note for k in ("iv_setting", "iv_account", "me 页"))


def should_mirror_for_hint(hint: str, *, rtl_mode: RtlMode) -> bool:
    if rtl_mode == "off":
        return False
    return str(hint).lower() not in _NO_MIRROR_HINTS


def resolve_step_mirror(
    step: dict[str, Any],
    *,
    hint: str,
    rtl_mode: RtlMode,
) -> bool:
    override = step_mirror_override(step)
    if override is not None:
        return override
    if rtl_mode == "off":
        return False
    # 底栏 / Me 顶栏为原生 chrome，内容帧为 WebView 时仍须镜像
    if _is_bottom_bar_step(step) or _is_native_me_chrome_step(step):
        return True
    return should_mirror_for_hint(hint, rtl_mode=rtl_mode)
