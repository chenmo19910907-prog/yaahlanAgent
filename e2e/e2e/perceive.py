"""识别：读取当前手机屏幕（快路径优先，单步预算内）。"""

from __future__ import annotations

import subprocess
import time
from typing import Any

from .adb_bridge import adb_execute, parse_json_stdout
from .budget import StepBudget


def perceive_for_step(*, budget: StepBudget, with_image: bool = False) -> dict[str, Any]:
    """步前识别：`observe --fast`，限制 ui_limit。"""
    args = ["observe", "--fast", "--ui-limit", str(budget.ui_limit)]
    if with_image:
        args.append("--image")

    code, stdout, stderr = adb_execute(args, timeout_s=budget.subprocess_timeout_s)
    if code != 0:
        raise RuntimeError(stderr.strip() or stdout.strip() or "observe 失败")
    payload = parse_json_stdout(stdout)
    payload["perceivedAt"] = time.time()
    return payload


def perceive_fresh(*, budget: StepBudget, wait_sec: float = 2.0) -> dict[str, Any]:
    """强制刷新 UI 树（observe --wait），用于登录页 stale 纠偏。"""
    wait_sec = max(0.5, wait_sec)
    args = [
        "observe",
        "--fast",
        "--ui-limit",
        str(budget.ui_limit),
        "--wait",
        str(wait_sec),
    ]
    timeout = max(budget.subprocess_timeout_s, 15.0) + wait_sec
    try:
        code, stdout, stderr = adb_execute(args, timeout_s=timeout)
    except subprocess.TimeoutExpired:
        return perceive_for_step(budget=budget, with_image=False)
    if code != 0:
        return perceive_for_step(budget=budget, with_image=False)
    payload = parse_json_stdout(stdout)
    payload["perceivedAt"] = time.time()
    payload["perceiveFresh"] = True
    return payload


def perceive_activity(*, budget: StepBudget) -> dict[str, Any]:
    """轻量识别：仅 Activity（~100–300ms）。"""
    code, stdout, stderr = adb_execute(["activity"], timeout_s=min(budget.subprocess_timeout_s, 1.5))
    if code != 0:
        raise RuntimeError(stderr.strip() or stdout.strip() or "activity 失败")
    data = parse_json_stdout(stdout)
    return data


def perceive_after_act(
    baseline: dict[str, Any],
    *,
    budget: StepBudget,
    remaining_ms: int,
) -> dict[str, Any]:
    """步后验收：默认 activity；预算充裕时用 observe --wait。"""
    base_act = _activity_name(baseline)

    if budget.post_act_mode == "wait_observe" and remaining_ms >= 600:
        wait_sec = min(budget.post_act_wait_sec, remaining_ms / 1000.0 - 0.2)
        wait_sec = max(0.2, wait_sec)
        args = ["observe", "--fast", "--ui-limit", str(budget.ui_limit), "--wait", str(wait_sec)]
        code, stdout, stderr = adb_execute(args, timeout_s=min(budget.subprocess_timeout_s, wait_sec + 1.0))
        if code == 0:
            screen = parse_json_stdout(stdout)
            cur = _activity_name(screen)
            return {
                "mode": "wait_observe",
                "summary": screen_summary(screen),
                "activityChanged": bool(base_act and cur and cur != base_act),
                "uiHash": screen.get("uiHash"),
            }

    act = perceive_activity(budget=budget)
    cur = _activity_name({"activity": act})
    return {
        "mode": "activity",
        "activity": act,
        "activityChanged": bool(base_act and cur and cur != base_act),
    }


def _activity_name(screen: dict[str, Any]) -> str:
    activity = screen.get("activity")
    if isinstance(activity, dict):
        return str(activity.get("activity") or activity.get("shortActivity") or "")
    return str(activity or "")


def screen_summary(screen: dict[str, Any]) -> str:
    act_name = _activity_name(screen) or "unknown"
    ui = screen.get("ui") if isinstance(screen.get("ui"), dict) else {}
    count = ui.get("elementCount", 0)
    labels: list[str] = []
    for item in ui.get("clickables") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if label and label not in labels:
            labels.append(label[:32])
        if len(labels) >= 6:
            break
    hint = "、".join(labels) if labels else "—"
    return f"Activity={act_name}；可点≈{count}；{hint}"
