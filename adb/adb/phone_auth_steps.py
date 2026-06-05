"""手机号登录/注册 UI 步骤组装。"""

from __future__ import annotations

from typing import Any

from .macros import apply_skip_flags, resolve_macro


def build_phone_login_steps(phone: str) -> list[dict[str, Any]]:
    """统一手机号登录流程（注册登录模块，非首页/Me/房间）。"""
    spec = resolve_macro("手机号登录", text=phone)
    steps: list[dict[str, Any]] = []
    for step in spec.get("steps", []):
        if not isinstance(step, dict):
            continue
        steps.append(dict(step))
    return apply_skip_flags(steps, skip={"login_lang", "dismiss_popup_taps"})


def build_phone_auth_steps(phone: str) -> list[dict[str, Any]]:
    """手机号 + 验证码（不含登录后弹窗处理）。"""
    skip_post = {"登录后处理弹窗", "login-post-popups", "login-dismiss-popup"}
    steps: list[dict[str, Any]] = []
    for step in build_phone_login_steps(phone):
        if step.get("run_script") in skip_post:
            continue
        steps.append(step)
    return steps


def build_register_profile_steps(phone: str) -> list[dict[str, Any]]:
    spec = resolve_macro("完成注册", text=phone)
    return list(spec.get("steps") or [])
