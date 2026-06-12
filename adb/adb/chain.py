"""连续操作链：确定路径可一次截图后多点，仅在边界再截图。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Literal

from .fragment_locator import build_locator_patch, persist_fragment_locator_updates
from .ui_locator import probe_locator_at_point

from .actions import clear_input_field, input_text, keyevent, swipe, tap
from .activity import get_foreground_activity, wait_for_activity
from .ui_locator import LocatorNotFoundError, is_locator_step, resolve_tap_from_step
from .rtl import RtlMode, mirror_x_pixel, resolve_step_mirror
from .device import AdbError, display_size
from .device_profile import (
    adapt_steps,
    adaptation_payload,
    resolve_adaptation,
)
from .screenshot import DEFAULT_CAPTURE_MAX_EDGE, capture_screenshot

CaptureMode = Literal["never", "start", "end", "both"]

_STEP_TYPES = frozenset(
    {
        "sleep",
        "tap",
        "tap_pct",
        "swipe",
        "key",
        "text",
        "capture",
        "launch_app",
        "run_script",
        "verify_splash",
        "popup_gate",
        "logcat_check",
        "wait_activity",
    }
)


def _resolve_tap(
    step: dict[str, Any],
    *,
    serial: str,
    width: int,
    height: int,
    mirror_x: bool = False,
    prefer_coords: bool = False,
) -> tuple[int, int, dict[str, Any] | None]:
    if is_locator_step(step):
        hit = resolve_tap_from_step(
            step,
            serial=serial,
            width=width,
            height=height,
            mirror_x=mirror_x,
            prefer_coords=prefer_coords,
        )
        return int(hit["x"]), int(hit["y"]), hit
    raise ValueError(
        f"步骤缺少定位字段（tap/tap_pct/resourceId/accessibilityId/xpath/tap_locate）: {step}"
    )


def run_chain(
    *,
    serial: str,
    steps: list[dict[str, Any]],
    capture: CaptureMode = "end",
    screenshot_dir: Path,
    max_screenshots: int,
    use_adaptation: bool = True,
    text: str | None = None,
    skip: set[str] | None = None,
    popup_gate_auto: bool = False,
    popup_gate_momoid: str | None = None,
    capture_max_edge: int | None = DEFAULT_CAPTURE_MAX_EDGE,
    rtl_mode: RtlMode = "off",
    fragment_path: Path | None = None,
    learn_locators: bool = False,
    locator_updates: dict[int, dict[str, Any]] | None = None,
    fast_mode: bool = False,
) -> dict[str, Any]:
    if not steps:
        raise ValueError("steps 不能为空")

    adapt_ctx = resolve_adaptation(serial) if use_adaptation else None
    if adapt_ctx and adapt_ctx.status == "uncalibrated":
        raise AdbError(adapt_ctx.message)
    if adapt_ctx:
        steps = adapt_steps(steps, adapt_ctx)

    from .macros import apply_skip_flags
    from .popup_gate import (
        auto_popup_gate_after_chain,
        ensure_popups_cleared,
        infer_tab_from_step,
        resolve_gate_scene,
    )

    steps = apply_skip_flags(steps, skip=skip or set())

    width, height = display_size(serial)
    executed: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "serial": serial,
        "displayWidth": width,
        "displayHeight": height,
        "capture": capture,
        "stepsExecuted": executed,
    }
    if adapt_ctx:
        result["adaptation"] = adaptation_payload(adapt_ctx)
    if rtl_mode == "on":
        result["rtlMode"] = rtl_mode
    if learn_locators:
        result["learnLocators"] = True
    if fast_mode:
        result["fastMode"] = True
    pending_locators: dict[int, dict[str, Any]] = (
        locator_updates if locator_updates is not None else {}
    )

    def _current_hint() -> str:
        fa = get_foreground_activity(serial=serial)
        return str(fa.get("hint", "unknown"))

    def _do_capture(label: str) -> dict[str, Any]:
        cap = capture_screenshot(
            serial=serial,
            directory=screenshot_dir,
            max_keep=max_screenshots,
            max_edge=capture_max_edge,
        )
        cap["capturePoint"] = label
        result["screenshot"] = cap
        return cap

    if capture in ("start", "both"):
        _do_capture("start")

    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"步骤 {index} 须为 object")
        kind = step.get("type")
        if kind is None:
            if "run_script" in step:
                kind = "run_script"
            elif "verify_splash" in step:
                kind = "verify_splash"
            elif "popup_gate" in step:
                kind = "popup_gate"
            elif "logcat_check" in step:
                kind = "logcat_check"
            elif "wait_activity" in step:
                kind = "wait_activity"
            elif "launch_app" in step:
                kind = "launch_app"
            elif "sleep" in step or "sleep_ms" in step:
                kind = "sleep"
            elif is_locator_step(step):
                kind = "tap"
            elif "swipe" in step:
                kind = "swipe"
            elif "key" in step:
                kind = "key"
            elif "text" in step:
                kind = "text"
            elif step.get("capture"):
                kind = "capture"
            else:
                raise ValueError(f"步骤 {index} 无法识别: {step}")
        if kind not in _STEP_TYPES:
            raise ValueError(f"未知步骤类型 {kind!r}，支持: {sorted(_STEP_TYPES)}")

        entry: dict[str, Any] = {"index": index, "type": kind}
        if step.get("note"):
            entry["note"] = step["note"]
        if step.get("optional"):
            entry["optional"] = True

        if kind == "sleep":
            ms = int(step.get("sleep_ms", step.get("sleep", 0)))
            if fast_mode and ms > 0 and not step.get("fast_sleep") is False:
                ms = max(100, ms // 2)
            if ms > 0:
                time.sleep(ms / 1000.0)
            entry["sleepMs"] = ms
        elif kind == "tap":
            hint = _current_hint()
            mirror_x = resolve_step_mirror(step, hint=hint, rtl_mode=rtl_mode)
            try:
                x, y, locate_meta = _resolve_tap(
                    step,
                    serial=serial,
                    width=width,
                    height=height,
                    mirror_x=mirror_x,
                    prefer_coords=fast_mode,
                )
            except LocatorNotFoundError as exc:
                if step.get("optional"):
                    entry["skipped"] = True
                    entry["locatorError"] = str(exc)
                    executed.append(entry)
                    continue
                raise
            used_kind = locate_meta.get("locatorKind") if locate_meta else None
            if learn_locators and step.get("learn_locators") is not False:
                should_probe = used_kind in ("tap_pct", "tap") or not step.get(
                    "resourceId"
                )
                if should_probe:
                    probe = probe_locator_at_point(
                        serial=serial, x=x, y=y, width=width, height=height
                    )
                    if probe:
                        patch = build_locator_patch(
                            step, probe, used_locator_kind=used_kind
                        )
                        if patch:
                            pending_locators[index] = patch
                            entry["locatorLearned"] = patch
            tap(x=x, y=y, serial=serial)
            entry["x"] = x
            entry["y"] = y
            if locate_meta:
                entry["locatorKind"] = locate_meta.get("locatorKind")
                entry["locatorValue"] = locate_meta.get("locatorValue")
                if locate_meta.get("resourceIdShort"):
                    entry["resourceId"] = locate_meta.get("resourceIdShort")
                if locate_meta.get("accessibilityId"):
                    entry["accessibilityId"] = locate_meta.get("accessibilityId")
                if locate_meta.get("bounds"):
                    entry["bounds"] = locate_meta.get("bounds")
                if locate_meta.get("attempts"):
                    entry["locatorAttempts"] = locate_meta.get("attempts")
            if mirror_x:
                entry["rtlMirrored"] = True
                entry["activityHint"] = hint
            if step.get("tap_pct_ref"):
                entry["tapPctRef"] = step["tap_pct_ref"]
                entry["tapPct"] = step.get("tap_pct")
            tab = infer_tab_from_step(step)
            if tab:
                result["currentTab"] = tab
        elif kind == "swipe":
            sw = step["swipe"]
            if not isinstance(sw, dict):
                raise ValueError(f"swipe 须为 object: {step}")
            hint = _current_hint()
            mirror_x = resolve_step_mirror(step, hint=hint, rtl_mode=rtl_mode)
            x1, y1, x2, y2 = (
                int(sw["x1"]),
                int(sw["y1"]),
                int(sw["x2"]),
                int(sw["y2"]),
            )
            if mirror_x:
                x1 = mirror_x_pixel(x1, width=width)
                x2 = mirror_x_pixel(x2, width=width)
                entry["rtlMirrored"] = True
                entry["activityHint"] = hint
            swipe(
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                duration_ms=int(sw.get("duration_ms", 300)),
                serial=serial,
            )
            entry["swipe"] = dict(sw)
            if mirror_x:
                entry["swipe"]["x1"] = x1
                entry["swipe"]["x2"] = x2
        elif kind == "key":
            code = int(step["key"])
            keyevent(code=code, serial=serial)
            entry["key"] = code
        elif kind == "text":
            content = str(step["text"])
            if not content:
                raise ValueError(f"text 不能为空: {step}")
            if "clear_before_text" in step:
                clear_first = bool(step["clear_before_text"])
            else:
                clear_first = not fast_mode
            if clear_first:
                default_max = 12 if fast_mode else 64
                max_chars = int(step.get("clear_max_chars", default_max))
                clear_input_field(serial=serial, max_chars=max_chars)
                entry["cleared"] = True
            input_text(text=content, serial=serial, clear_first=False)
            entry["text"] = content
        elif kind == "capture":
            cap = _do_capture(f"step_{index}")
            entry["screenshot"] = cap["path"]
        elif kind == "launch_app":
            from .launch import launch_app as do_launch

            result["coldStartTime"] = int(time.time())
            app_key = str(step.get("launch_app", "yaahlan"))
            launch_info = do_launch(serial=serial, app_key=app_key)
            entry["launchApp"] = app_key
            entry["launch"] = launch_info
        elif kind == "verify_splash":
            from .splash_verify import verify_and_recover_splash
            from .tunnel_verify import resolve_momoid

            raw = step.get("verify_splash", True)
            recover = True
            momoid: str | None = None
            tunnel_wait = 20
            if isinstance(raw, dict):
                recover = bool(raw.get("recover", True))
                tunnel_wait = int(raw.get("tunnel_wait", tunnel_wait))
                account = raw.get("account")
                if raw.get("momoid"):
                    momoid = str(raw["momoid"])
                elif account:
                    momoid = resolve_momoid(account=str(account))
            elif isinstance(raw, bool):
                recover = raw

            cold_start = result.get("coldStartTime")
            if cold_start is None:
                cold_start = int(time.time()) - 45

            splash_out = verify_and_recover_splash(
                serial=serial,
                screenshot_dir=screenshot_dir,
                max_screenshots=max_screenshots,
                momoid=momoid,
                start_time=int(cold_start),
                recover=recover,
                tunnel_wait=tunnel_wait,
                use_adaptation=use_adaptation,
            )
            entry["verifySplash"] = splash_out
            result["splashVerify"] = splash_out
            if not splash_out.get("ok"):
                result["splashVerifyFailed"] = True
        elif kind == "popup_gate":
            from .tunnel_verify import resolve_momoid as _resolve_momoid

            raw = step.get("popup_gate", True)
            scene_arg = "auto"
            gate_momoid = popup_gate_momoid
            gate_dismiss = False
            if isinstance(raw, dict):
                scene_arg = str(raw.get("scene", "auto"))
                gate_dismiss = bool(raw.get("dismiss", False))
                if raw.get("momoid"):
                    gate_momoid = str(raw["momoid"])
                elif raw.get("account"):
                    gate_momoid = _resolve_momoid(account=str(raw["account"]))
            fa_now = get_foreground_activity(serial=serial)
            resolved = resolve_gate_scene(
                hint=str(fa_now.get("hint", "")),
                current_tab=str(result.get("currentTab", "")) or None,
                explicit=scene_arg,
            )
            if resolved is None:
                raise ValueError(
                    f"popup_gate 无法推断 scene（hint={fa_now.get('hint')}, "
                    f"currentTab={result.get('currentTab')!r}），请显式指定 scene"
                )
            gate = ensure_popups_cleared(
                serial=serial,
                scene=resolved,
                screenshot_dir=screenshot_dir,
                max_screenshots=max_screenshots,
                momoid=gate_momoid,
                max_edge=capture_max_edge,
                use_adaptation=use_adaptation,
                auto_dismiss=gate_dismiss,
            )
            entry["popupGate"] = gate
            result["popupGate"] = gate
            if gate.get("screenshot"):
                result["screenshot"] = gate["screenshot"]
            if gate.get("blocked") or not gate.get("ok"):
                result["popupGateFailed"] = True
        elif kind == "wait_activity":
            raw = step.get("wait_activity")
            if isinstance(raw, str):
                spec: dict[str, Any] = {"hint": raw.strip()}
            elif isinstance(raw, dict):
                spec = dict(raw)
            else:
                raise ValueError(f"wait_activity 须为 hint 字符串或 object: {step}")

            hints_raw = spec.get("hints")
            hints_list: list[str] | None = None
            if isinstance(hints_raw, list):
                hints_list = [str(h).strip() for h in hints_raw if str(h).strip()]

            wait_out = wait_for_activity(
                serial=serial,
                timeout_ms=int(spec.get("timeout_ms", spec.get("timeoutMs", 3000))),
                poll_ms=int(spec.get("poll_ms", spec.get("pollMs", 250))),
                hint=str(spec["hint"]).strip() if spec.get("hint") else None,
                hints=hints_list,
                short_name=str(spec.get("short_name", spec.get("shortName", ""))).strip()
                or None,
                package=str(spec.get("package", "")).strip() or None,
            )
            entry["waitActivity"] = wait_out
            entry["elapsedMs"] = wait_out.get("elapsedMs")
            result["lastWaitActivity"] = wait_out
            required = spec.get("required", True)
            if required is not False and not wait_out.get("matched"):
                expected = wait_out.get("expected", {})
                fa = wait_out.get("foregroundActivity")
                got = fa.get("hint") if isinstance(fa, dict) else "?"
                raise AdbError(
                    f"wait_activity 超时：期望 {expected}，当前 hint={got!r} "
                    f"（{wait_out.get('elapsedMs')}ms）"
                )
        elif kind == "logcat_check":
            from .logcat_check import parse_logcat_check_spec, wait_for_logcat

            raw = step.get("logcat_check", True)
            opts = parse_logcat_check_spec(raw)
            if opts is None:
                raise ValueError(f"logcat_check 须指定 grep/pattern: {step}")
            logcat_out = wait_for_logcat(opts, serial=serial)
            entry["logcatCheck"] = logcat_out
            result["logcatVerify"] = logcat_out
            if not logcat_out.get("ok"):
                result["logcatVerifyFailed"] = True
        elif kind == "run_script":
            from .recorded_scripts import load_fragment, resolve_key

            script_key = str(step["run_script"])
            block_skip = set(step.get("skip") or []) | (skip or set())
            frag = load_fragment(script_key, text=text)
            nested = apply_skip_flags(list(frag.get("steps", [])), skip=block_skip)
            _nested_id, _nested_name, nested_path = resolve_key(
                script_key, kind="fragment"
            )
            nested_updates: dict[int, dict[str, Any]] = {}
            sub = run_chain(
                serial=serial,
                steps=nested,
                capture="never",
                screenshot_dir=screenshot_dir,
                max_screenshots=max_screenshots,
                use_adaptation=use_adaptation,
                text=text,
                skip=block_skip,
                popup_gate_auto=False,
                rtl_mode=rtl_mode,
                fragment_path=nested_path,
                learn_locators=learn_locators,
                locator_updates=nested_updates,
                fast_mode=fast_mode,
            )
            entry["runScript"] = frag.get("name", script_key)
            entry["scriptId"] = frag.get("id", script_key)
            entry["nestedSteps"] = sub.get("stepsExecuted")
            if learn_locators and nested_updates:
                nested_persist = persist_fragment_locator_updates(
                    nested_path, nested_updates
                )
                entry["nestedLocatorPersist"] = nested_persist
                result.setdefault("locatorPersistNested", []).append(nested_persist)
            if sub.get("coldStartTime") and "coldStartTime" not in result:
                result["coldStartTime"] = sub["coldStartTime"]
            if sub.get("splashVerify"):
                result["splashVerify"] = sub["splashVerify"]
            if sub.get("splashVerifyFailed"):
                result["splashVerifyFailed"] = True
            if sub.get("currentTab"):
                result["currentTab"] = sub["currentTab"]
            if sub.get("popupGate"):
                result["popupGate"] = sub["popupGate"]
            if sub.get("popupGateFailed"):
                result["popupGateFailed"] = True

        executed.append(entry)

    if popup_gate_auto and not result.get("popupGate"):
        gate = auto_popup_gate_after_chain(
            serial=serial,
            chain_result=result,
            screenshot_dir=screenshot_dir,
            max_screenshots=max_screenshots,
            momoid=popup_gate_momoid,
            max_edge=capture_max_edge,
            use_adaptation=use_adaptation,
        )
        if gate:
            result["popupGate"] = gate
            if gate.get("screenshot"):
                result["screenshot"] = gate["screenshot"]
            if gate.get("blocked") or not gate.get("ok"):
                result["popupGateFailed"] = True

    if capture in ("end", "both") and "screenshot" not in result:
        _do_capture("end")
    elif capture == "never":
        result["screenshot"] = None

    if learn_locators and fragment_path is not None and pending_locators:
        persist_out = persist_fragment_locator_updates(
            fragment_path, pending_locators
        )
        result["locatorPersist"] = persist_out
        if persist_out.get("changed"):
            result["locatorLearnedSteps"] = persist_out.get("changedSteps", [])

    return result


def load_steps_file(path: Path) -> tuple[list[dict[str, Any]], CaptureMode]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("步骤文件根节点须为 object")
    capture = data.get("capture", "end")
    if capture not in ("never", "start", "end", "both"):
        raise ValueError(f"capture 无效: {capture}")
    steps = data.get("steps")
    if not isinstance(steps, list):
        raise ValueError("steps 须为数组")
    return steps, capture
