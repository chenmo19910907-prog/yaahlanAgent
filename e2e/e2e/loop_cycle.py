"""单步流水线：识别 → 思考 → 执行（带 3s 预算）。"""

from __future__ import annotations

import time
from typing import Any

from .act import execute_plan
from .budget import StepBudget, StepTimer
from .perceive import perceive_after_act, perceive_for_step, screen_summary
from .login_language import (
    _FRESH_PERCEIVE_STEPS,
    _LOGIN_TEXT_STEPS,
    _NAV_FAST_STEPS,
    unblock_login_screen,
)
from .scene_gate import check_expect_after, observe_tree_stale, should_retry_perceive
from .perceive import perceive_activity, perceive_fresh
from .step_hints import case_modules, lookup_step_hint
from .think import think_step

_last_ui_hash: str | None = None


def run_step_cycle(
    *,
    nl_step: str,
    case: dict[str, Any],
    kb_hints: list[str],
    budget: StepBudget | None = None,
    with_image: bool = False,
) -> dict[str, Any]:
    """执行一步完整循环，返回分阶段耗时。"""
    global _last_ui_hash
    budget = budget or StepBudget()
    timer = StepTimer(budget=budget)
    step_hint = lookup_step_hint(case_modules(case), nl_step)

    t0 = time.perf_counter()
    intent_probe = (nl_step or "").strip()
    skip_perceive = (
        intent_probe.startswith("启动")
        or intent_probe.startswith("打开")
        or intent_probe.startswith("清除")
        or intent_probe.startswith("确保")
        or intent_probe.startswith("截图")
        or intent_probe.startswith("截屏")
        or intent_probe.startswith("处理")
    )
    perceive_retried = False
    if skip_perceive:
        screen = {"activity": {}, "ui": {}, "skippedPerceive": True}
        timer.mark("perceive", 0)
    elif nl_step in (_NAV_FAST_STEPS | _LOGIN_TEXT_STEPS) and not with_image:
        activity = perceive_activity(budget=budget)
        screen = {"activity": activity, "ui": {}, "perceiveLite": True}
        timer.mark("perceive", int((time.perf_counter() - t0) * 1000))
    else:
        if nl_step in _FRESH_PERCEIVE_STEPS and not with_image:
            perceive_retried = True
            screen = unblock_login_screen(budget=budget)
        else:
            screen = perceive_for_step(budget=budget, with_image=with_image)
        if nl_step not in _FRESH_PERCEIVE_STEPS and should_retry_perceive(screen, prev_ui_hash=_last_ui_hash) and not with_image:
            perceive_retried = True
            if observe_tree_stale(screen):
                screen = unblock_login_screen(budget=budget, screen=screen)
            else:
                screen = perceive_fresh(budget=budget, wait_sec=1.5)
        _last_ui_hash = str(screen.get("uiHash") or "") or _last_ui_hash
        timer.mark("perceive", int((time.perf_counter() - t0) * 1000))

    t1 = time.perf_counter()
    plan = think_step(nl_step=nl_step, screen=screen, case=case, kb_hints=kb_hints)
    timer.mark("think", int((time.perf_counter() - t1) * 1000))

    scene_gate_before = plan.meta.get("sceneGate") if isinstance(plan.meta, dict) else None

    t2 = time.perf_counter()
    if plan.action in {"scene_blocked", "need_agent", "abort", "unsupported"}:
        act_result = {"ok": False, "action": plan.action, "skipped": True, "error": plan.reasoning}
    elif plan.action == "skip":
        act_result = {"ok": True, "action": "skip", "skipped": True, "reason": plan.reasoning}
    elif plan.action == "verify":
        act_result = {"ok": True, "action": "verify", "skipped": False}
    else:
        act_result = execute_plan(plan, timeout_s=budget.subprocess_timeout_s, budget=budget)
    timer.mark("act", int((time.perf_counter() - t2) * 1000))

    if act_result.get("ok") and plan.action in {
        "clear_app",
        "launch",
        "ensure_english",
        "dismiss_permission",
    }:
        _last_ui_hash = None

    if act_result.get("ok") and plan.action == "wait" and nl_step in {"等待5秒", "等待4秒"}:
        _last_ui_hash = None

    post: dict[str, Any] | None = None
    scene_gate_after: dict[str, Any] | None = None
    if act_result.get("ok") and plan.action in {"tap", "text", "back", "launch", "swipe"}:
        remaining = timer.remaining_ms()
        if remaining > 150 and budget.post_act_mode != "skip":
            t3 = time.perf_counter()
            post = perceive_after_act(screen, budget=budget, remaining_ms=remaining)
            timer.mark("postAct", int((time.perf_counter() - t3) * 1000))
            if step_hint and isinstance(post, dict):
                activity = post.get("activity") if isinstance(post.get("activity"), dict) else {}
                scene_gate_after = check_expect_after(activity, step_hint)
                post["sceneGate"] = scene_gate_after
    elif act_result.get("ok") and plan.action == "clear_app":
        pass
    elif act_result.get("ok") and plan.action in {"ensure_english", "dismiss_permission", "capture"}:
        pass
    elif act_result.get("ok") and plan.action == "wait" and step_hint and step_hint.get("expectSceneAfter"):
        t3 = time.perf_counter()
        activity = perceive_activity(budget=budget)
        post = {"mode": "activity", "activity": activity}
        scene_gate_after = check_expect_after(activity, step_hint)
        post["sceneGate"] = scene_gate_after
        timer.mark("postAct", int((time.perf_counter() - t3) * 1000))

    timing = timer.to_dict()
    return {
        "step": nl_step,
        "perceive": {
            "summary": screen_summary(screen),
            "activity": screen.get("activity"),
            "uiHash": screen.get("uiHash"),
            "retried": perceive_retried,
        },
        "think": plan.to_dict(),
        "act": act_result,
        "postAct": post,
        "sceneGateBefore": scene_gate_before,
        "sceneGateAfter": scene_gate_after,
        "timingMs": timing,
    }
