"""执行：将思考层 Plan 落到 e2e 驱动（launch/driver + 读屏 locate）。"""

from __future__ import annotations

import time
from typing import Any

from . import driver
from .adb_bridge import adb_execute, adb_execute_act, parse_json_stdout
from .think import Plan


def execute_plan(plan: Plan, *, timeout_s: float = 2.5, budget: Any | None = None) -> dict[str, Any]:
    action = plan.action

    if action == "clear_app":
        app_key = str(plan.meta.get("app") or "yaahlan")
        try:
            return driver.clear_app_data(app_key)
        except (RuntimeError, ValueError) as exc:
            return {"ok": False, "action": action, "error": str(exc)}

    if action == "launch":
        app_key = str(plan.meta.get("app") or "yaahlan")
        wait_ms = int(plan.meta.get("waitMs") or 4000)
        try:
            result = driver.launch_app(app_key, wait_ms=wait_ms)
            return result
        except (RuntimeError, ValueError) as exc:
            return {"ok": False, "action": action, "error": str(exc)}

    if action == "wait":
        time.sleep(max(plan.wait_sec, 0.1))
        return {"ok": True, "action": action, "waitSec": plan.wait_sec}

    if action == "back":
        try:
            return driver.key_event(4, timeout_s=timeout_s)
        except RuntimeError as exc:
            return {"ok": False, "action": action, "error": str(exc)}

    if action == "swipe":
        cfg = plan.meta.get("swipe") if isinstance(plan.meta, dict) else {}
        if not isinstance(cfg, dict) or not cfg:
            w, h = driver.display_size(timeout_s=timeout_s)
            cfg = {"x1_pct": 0.5, "y1_pct": 0.34, "x2_pct": 0.5, "y2_pct": 0.73}
        w, h = driver.display_size(timeout_s=timeout_s)
        try:
            return driver.swipe(
                int(float(cfg.get("x1_pct", 0.5)) * w),
                int(float(cfg.get("y1_pct", 0.34)) * h),
                int(float(cfg.get("y2_pct", 0.73)) * h),
                x2=int(float(cfg.get("x2_pct", 0.5)) * w),
                duration_ms=int(cfg.get("duration_ms") or 300),
                timeout_s=timeout_s,
            )
        except RuntimeError as exc:
            return {"ok": False, "action": action, "error": str(exc)}

    if action == "tap":
        if plan.center and len(plan.center) >= 2:
            try:
                return driver.tap_xy(int(plan.center[0]), int(plan.center[1]), timeout_s=timeout_s)
            except RuntimeError as exc:
                return {"ok": False, "action": action, "error": str(exc)}

        if plan.resource_id:
            code, stdout, stderr = adb_execute(
                ["locate", "--resource-id", plan.resource_id],
                timeout_s=timeout_s,
            )
            if code == 0:
                try:
                    loc = parse_json_stdout(stdout)
                    center = loc.get("center") if isinstance(loc.get("center"), list) else None
                    if center and len(center) >= 2:
                        out = driver.tap_xy(int(center[0]), int(center[1]), timeout_s=timeout_s)
                        out["resourceId"] = plan.resource_id
                        return out
                except (ValueError, TypeError):
                    pass
            code2, stdout2, stderr2 = adb_execute_act(
                ["locate", "--resource-id", plan.resource_id, "--tap"],
                timeout_s=timeout_s,
            )
            if code2 == 0:
                return {
                    "ok": True,
                    "action": action,
                    "resourceId": plan.resource_id,
                    "stdout": stdout2.strip(),
                    "stderr": stderr2.strip(),
                }

        if plan.tap_pct and len(plan.tap_pct) >= 2:
            try:
                return driver.tap_pct(plan.tap_pct, timeout_s=timeout_s)
            except RuntimeError as exc:
                return {"ok": False, "action": action, "error": str(exc)}

        if plan.resource_id:
            return {
                "ok": False,
                "action": action,
                "resourceId": plan.resource_id,
                "error": "locate 未命中且无 tapPct",
            }
        return {"ok": False, "action": action, "error": "缺少坐标或 resourceId"}

    if action == "dismiss_permission":
        from .login_language import dismiss_location_permission_if_present

        return dismiss_location_permission_if_present()

    if action == "ensure_english":
        from .budget import StepBudget
        from .login_language import run_until_english

        return run_until_english(
            budget=budget if budget is not None else StepBudget(),
            timeout_s=timeout_s,
        )

    if action == "capture":
        import shutil
        from pathlib import Path

        max_edge = 1170
        if isinstance(plan.meta, dict) and plan.meta.get("maxEdge"):
            max_edge = int(plan.meta["maxEdge"])
        cap_timeout = max(timeout_s, 15.0)
        code, stdout, stderr = adb_execute_act(
            ["capture", "--max-edge", str(max_edge)],
            timeout_s=cap_timeout,
        )
        if code != 0:
            return {
                "ok": False,
                "action": action,
                "error": (stderr or stdout or "capture 失败").strip(),
            }
        try:
            data = parse_json_stdout(stdout)
        except ValueError as exc:
            return {"ok": False, "action": action, "error": str(exc)}
        src = Path(str(data.get("path") or ""))
        if not src.is_file():
            return {"ok": False, "action": action, "error": f"截图文件不存在: {src}"}
        dest_path = ""
        if isinstance(plan.meta, dict) and plan.meta.get("destPath"):
            dest = Path(str(plan.meta["destPath"]))
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            dest_path = str(dest)
        return {
            "ok": True,
            "action": action,
            "src": str(src),
            "dest": dest_path,
            "activity": data.get("activity"),
        }

    if action == "text":
        if not plan.text:
            return {"ok": False, "action": action, "error": "缺少输入文本"}
        clear_first = bool(isinstance(plan.meta, dict) and plan.meta.get("clearBefore"))
        try:
            return driver.input_text(
                plan.text,
                timeout_s=max(timeout_s, 15.0),
                clear_first=clear_first,
            )
        except RuntimeError as exc:
            return {"ok": False, "action": action, "error": str(exc)}

    if action in {"need_agent", "unsupported", "abort", "verify", "scene_blocked", "skip", "clear_app"}:
        return {"ok": action in {"verify", "skip", "clear_app"}, "action": action, "skipped": action not in {"verify", "clear_app"}}

    return {"ok": False, "action": action, "error": "未知 action"}
