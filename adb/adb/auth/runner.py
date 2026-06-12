"""手机号登录 / 注册 UI 步骤统一执行。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from ..chain import run_chain
from ..macros import apply_skip_flags, resolve_macro
from ..phone_auth_steps import (
    build_phone_auth_steps,
    build_phone_login_steps,
    build_register_profile_steps,
)

CaptureMode = Literal["never", "start", "end", "both"]


def run_steps(
    steps: list[dict[str, Any]],
    *,
    serial: str,
    shot_dir: Path,
    max_screenshots: int = 2,
    capture: CaptureMode = "end",
    use_adaptation: bool = True,
    text: str | None = None,
    skip: set[str] | None = None,
    popup_gate_auto: bool = False,
    rtl_mode: str = "off",
    fast_mode: bool = True,
) -> dict[str, Any]:
    """底层：对步骤列表跑 chain（login / sweep / macro 共用）。"""
    return run_chain(
        serial=serial,
        steps=steps,
        capture=capture,
        screenshot_dir=shot_dir,
        max_screenshots=max_screenshots,
        use_adaptation=use_adaptation,
        text=text,
        skip=skip,
        popup_gate_auto=popup_gate_auto,
        rtl_mode=rtl_mode,  # type: ignore[arg-type]
        learn_locators=False,
        fast_mode=fast_mode,
    )


def run_macro_by_name(
    name: str,
    *,
    serial: str,
    shot_dir: Path,
    text: str | None = None,
    skip: set[str] | None = None,
    max_screenshots: int = 2,
    capture: CaptureMode = "end",
    use_adaptation: bool = True,
    popup_gate_auto: bool = True,
    rtl_mode: str = "off",
) -> dict[str, Any]:
    spec = resolve_macro(name, text=text)
    steps = apply_skip_flags(list(spec.get("steps", [])), skip=skip or set())
    return run_steps(
        steps,
        serial=serial,
        shot_dir=shot_dir,
        max_screenshots=max_screenshots,
        capture=capture,
        use_adaptation=use_adaptation,
        text=text,
        skip=skip,
        popup_gate_auto=popup_gate_auto,
        rtl_mode=rtl_mode,
    )


def run_phone_login(
    phone: str,
    *,
    serial: str,
    shot_dir: Path,
    max_screenshots: int = 2,
    include_post_login_popup: bool = True,
    popup_gate_auto: bool = False,
) -> dict[str, Any]:
    """完整手机号登录（含登录后处理弹窗片段，skip login_lang）。"""
    skip: set[str] = {"login_lang"}
    if not include_post_login_popup:
        skip |= {"login_post", "login_post_popups"}
    return run_steps(
        build_phone_login_steps(phone),
        serial=serial,
        shot_dir=shot_dir,
        max_screenshots=max_screenshots,
        capture="end",
        skip=skip,
        popup_gate_auto=popup_gate_auto,
    )


def run_phone_auth_only(
    phone: str,
    *,
    serial: str,
    shot_dir: Path,
    max_screenshots: int = 2,
) -> dict[str, Any]:
    """验证码登录 UI，不含登录后弹窗与注册资料。"""
    return run_steps(
        build_phone_auth_steps(phone),
        serial=serial,
        shot_dir=shot_dir,
        max_screenshots=max_screenshots,
        capture="never",
        popup_gate_auto=False,
    )


def run_register_profile(
    phone: str,
    *,
    serial: str,
    shot_dir: Path,
    max_screenshots: int = 2,
) -> dict[str, Any]:
    return run_steps(
        build_register_profile_steps(phone),
        serial=serial,
        shot_dir=shot_dir,
        max_screenshots=max_screenshots,
        capture="end",
        popup_gate_auto=False,
    )
