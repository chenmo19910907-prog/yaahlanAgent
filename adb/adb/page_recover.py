"""落点不符预期时：截图 + AI 读图纠偏（禁止 force-stop / 房间首页 Me 固定脚本）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .activity import get_foreground_activity
from .ai_operate import GOAL_SPECS, prepare_vision_cycle


def recover_toward_hint(
    *,
    serial: str,
    expect_hint: str,
    screenshot_dir: Path,
    max_screenshots: int,
    max_passes: int = 6,
    use_adaptation: bool = True,
) -> dict[str, Any]:
    """
    落点与 expect_hint 不符：返回 screenshot + workflow，由 Agent 读图操作。
    **不会** force-stop 或跑首页/Me/房间固定 macro。
    """
    del max_passes, use_adaptation  # AI 模式不在此自动连点

    expect_hint = expect_hint.strip()
    if expect_hint not in ("home", "login", "in_room", "search"):
        raise ValueError(f"expect_hint 不支持 {expect_hint!r}")

    fa = get_foreground_activity(serial=serial)
    hint = str(fa.get("hint", ""))
    if hint == expect_hint:
        out = prepare_vision_cycle(
            goal="recover",
            serial=serial,
            screenshot_dir=screenshot_dir,
            max_screenshots=max_screenshots,
            note=f"已达 {expect_hint}。",
        )
        out["ok"] = True
        out["requiresAiVision"] = False
        return out

    goal = _goal_for_expect(expect_hint, hint)
    out = prepare_vision_cycle(
        goal=goal,
        serial=serial,
        screenshot_dir=screenshot_dir,
        max_screenshots=max_screenshots,
        note=f"当前 hint={hint}，期望 {expect_hint}。",
    )
    out["expectHint"] = expect_hint
    out["foregroundActivityBefore"] = fa
    spec = GOAL_SPECS.get(goal, {})
    out["agentHint"] = (
        f"落点不符（当前 hint={hint}，期望 {expect_hint}）。"
        f"读 screenshot，按 workflow 用 tap/key 纠偏；目标：{spec.get('label', goal)}。"
        f"勿 macro 固定坐标、勿 force-stop。"
    )
    return out


def reset_stuck_before_logout(
    *,
    serial: str,
    screenshot_dir: Path,
    max_screenshots: int,
    use_adaptation: bool = True,
) -> dict[str, Any]:
    """退出登录前：截图 + AI 工作流（不跑固定 macro）。"""
    del use_adaptation
    fa = get_foreground_activity(serial=serial)
    hint = str(fa.get("hint", ""))
    if hint == "login":
        out = prepare_vision_cycle(
            goal="logout",
            serial=serial,
            screenshot_dir=screenshot_dir,
            max_screenshots=max_screenshots,
        )
        out["ok"] = True
        out["requiresAiVision"] = False
        out["skipped"] = True
        return out

    if hint in ("in_room", "search", "webview"):
        goal = "exit_room" if hint == "in_room" else "recover"
    else:
        goal = "logout"

    out = prepare_vision_cycle(
        goal=goal,
        serial=serial,
        screenshot_dir=screenshot_dir,
        max_screenshots=max_screenshots,
        note=f"退出前纠偏 hint={hint}。",
    )
    out["preLogout"] = True
    return out


def _goal_for_expect(expect: str, current: str) -> str:
    if expect == "login":
        return "logout"
    if expect == "in_room":
        return "enter_room"
    if expect == "home":
        if current in ("in_room", "search"):
            return "exit_room"
        return "home_tab"
    if expect == "search" and current == "in_room":
        return "exit_room"
    return "recover"
