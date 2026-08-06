"""登录前 MOA 查号：有 userId 走登录，无 userId 走注册。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .activity import get_foreground_activity
from .auth.runner import (
    run_phone_auth_only,
    run_phone_login,
    run_register_profile,
)
from .device import AdbError, require_device
from .phone_login_status import query_phone_login_status
from .post_login_verify import verify_and_dismiss_post_login
from .screenshot import screenshot_dir


def enter_account(
    phone: str,
    *,
    serial: str | None = None,
    shot_dir: Path | None = None,
    max_screenshots: int = 3,
    skip_moa_check: bool = False,
    force_route: str | None = None,
) -> dict[str, Any]:
    """
    登录/注册统一入口：先 MOA 查手机号是否有关联 userId。
    - registered → macro 手机号登录 + postLogin 验收
    - 未注册 → 手机验证码 + 完善资料 + 跳过头像引导
    """
    serial = serial or require_device(None)
    shot_dir = shot_dir or screenshot_dir(None)
    mobile = str(phone).strip()
    if not mobile:
        raise ValueError("phone 不能为空")

    out: dict[str, Any] = {"phone": mobile, "ok": False}

    fa0 = get_foreground_activity(serial=serial)
    if fa0.get("hint") not in ("login", "register"):
        from .launch import launch_app
        from .project_paths import get_project_id

        launch_app(serial=serial, app_key=get_project_id())
        time.sleep(2)

    if skip_moa_check:
        status = {
            "ok": True,
            "phone": mobile,
            "registered": force_route == "login",
            "userId": None,
            "route": force_route or "login",
            "skippedMoa": True,
        }
    else:
        status = query_phone_login_status(mobile)
    out["phoneLoginStatus"] = status
    route = force_route or status.get("route") or (
        "login" if status.get("registered") else "register"
    )
    out["route"] = route

    login_start = int(time.time())

    if route == "login":
        run_phone_login(
            mobile,
            serial=serial,
            shot_dir=shot_dir,
            max_screenshots=max_screenshots,
            popup_gate_auto=False,
        )
        momoid = status.get("userId")
        post_login = verify_and_dismiss_post_login(
            serial=serial,
            screenshot_dir=shot_dir,
            max_screenshots=max_screenshots,
            momoid=momoid,
            login_start=login_start,
        )
        fa = post_login.get("foregroundActivity") or get_foreground_activity(
            serial=serial
        )
        out["postLogin"] = post_login
        out["foregroundActivity"] = fa
        out["ok"] = bool(post_login.get("ok")) and fa.get("hint") == "home"
        out["agentHint"] = (
            "登录成功，activity hint=home。"
            if out["ok"]
            else "登录未完成：查 postLogin / foregroundActivity。"
        )
        return out

    if route != "register":
        raise AdbError(f"未知 route: {route!r}")

    run_phone_auth_only(
        mobile,
        serial=serial,
        shot_dir=shot_dir,
        max_screenshots=max_screenshots,
    )
    fa_after_code = get_foreground_activity(serial=serial)
    out["afterVerifyActivity"] = fa_after_code
    if fa_after_code.get("shortName") != "RegisterInfoActivity":
        out["agentHint"] = (
            "验证码后未到 RegisterInfoActivity；"
            f"当前 {fa_after_code.get('shortName')}。"
            "若 MOA 显示未注册但 App 进首页，请核对 MOA 与 App 环境。"
        )
        return out

    run_register_profile(
        mobile,
        serial=serial,
        shot_dir=shot_dir,
        max_screenshots=max_screenshots,
    )
    reg_end = int(time.time())
    reg_status = query_phone_login_status(mobile)
    out["registeredUserId"] = reg_status.get("userId")
    post_login = verify_and_dismiss_post_login(
        serial=serial,
        screenshot_dir=shot_dir,
        max_screenshots=max_screenshots,
        momoid=reg_status.get("userId"),
        login_start=reg_end - 5,
        force_dismiss=True,
        dismiss_home_popups=True,
    )
    fa = post_login.get("foregroundActivity") or get_foreground_activity(
        serial=serial
    )
    out["postLogin"] = post_login
    out["foregroundActivity"] = fa
    out["ok"] = bool(reg_status.get("registered")) and fa.get("hint") == "home"
    out["agentHint"] = (
        f"注册成功 userId={reg_status.get('userId')}，activity hint=home。"
        if out["ok"]
        else f"注册后落点 hint={fa.get('hint')}；查 postLogin。"
    )
    return out
