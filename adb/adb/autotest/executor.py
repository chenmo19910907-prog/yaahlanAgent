"""执行自动化用例（支持 macro 片段与内联 steps，不必依赖已录制片段）。"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any, Literal

from ..account_availability import check_account
from ..actions import input_text, keyevent, swipe, tap
from ..ai_operate import assert_fragment_script_allowed
from ..chain import run_chain
from ..cli_finalize import attach_foreground_activity
from ..cli_runner import run_macro_command
from ..device import display_size
from ..screenshot import capture_screenshot
from ..tunnel_verify import TunnelVerifyOptions, resolve_momoid, wait_for_tunnel
from .loader import load_case
from .verify import run_verify_point

CaptureMode = Literal["never", "start", "end", "both"]


def _resolve_value(expr: str, account: dict[str, Any]) -> str:
    text = str(expr or "").strip()
    if text.startswith("account."):
        return str(account.get(text.split(".", 1)[1], "")).strip()
    return text


def _tunnel_verify_from_op(
    op: dict[str, Any],
    *,
    account: dict[str, Any],
    start_time: int,
) -> dict[str, Any] | None:
    tunnel = op.get("tunnel")
    if not isinstance(tunnel, dict):
        return None
    keyword = str(tunnel.get("keyword") or "").strip()
    if not keyword:
        return None
    alias = _resolve_value(str(tunnel.get("account") or "account.alias"), account)
    momoid = resolve_momoid(
        momoid=str(tunnel.get("momoid") or "").strip() or None,
        account=alias or str(account.get("alias") or ""),
    )
    expect_ec = tunnel.get("expectEc")
    opts = TunnelVerifyOptions(
        momoid=momoid,
        keyword=keyword,
        wait_seconds=int(tunnel.get("waitSeconds") or 30),
        poll_interval_ms=int(tunnel.get("pollIntervalMs") or 2000),
        expect_response_ec=int(expect_ec) if expect_ec is not None else 200,
        since_buffer_seconds=int(tunnel.get("sinceBufferSeconds") or 5),
        g_appid=str(tunnel.get("gAppid") or "All"),
        g_env=str(tunnel.get("gEnv") or "alpha"),
        min_matches=int(tunnel.get("minMatches") or 1),
    )
    return wait_for_tunnel(opts, start_time=start_time)


def _make_macro_args(
    *,
    serial: str,
    script: str,
    text: str | None,
    shot_dir: Path,
    max_screenshots: int,
    tunnel_account: str | None,
    tunnel_keyword: str | None,
    tunnel_wait: int,
    tunnel_expect_ec: int | None,
    popup_scene: str | None,
    popup_auto_dismiss: bool,
    no_capture: bool,
    force_script: bool,
) -> argparse.Namespace:
    return argparse.Namespace(
        name=script,
        text=text,
        skip=[],
        capture="never" if no_capture else None,
        no_capture=no_capture,
        fast=False,
        no_adapt=False,
        no_popup_gate=False,
        force_script=force_script,
        rtl=False,
        no_rtl=False,
        tunnel_account=tunnel_account,
        tunnel_momoid=None,
        tunnel_keyword=tunnel_keyword,
        tunnel_wait=tunnel_wait,
        tunnel_expect_ec=tunnel_expect_ec,
        tunnel_g_appid="All",
        tunnel_g_env="alpha",
        popup_scene=popup_scene,
        popup_auto_dismiss=popup_auto_dismiss,
        popup_since=120,
        logcat_grep=None,
        logcat_wait=10,
        logcat_tail=300,
        logcat_clear_first=False,
        logcat_regex=False,
        logcat_invert=False,
        logcat_no_app_filter=False,
        max_edge=None,
        learn_locators=False,
        serial=serial,
        max_screenshots=max_screenshots,
        screenshot_dir=shot_dir,
        dump_body=False,
    )


def _resolve_capture_mode(op: dict[str, Any]) -> CaptureMode:
    capture = str(op.get("capture") or "end").strip().lower()
    if op.get("noCapture"):
        return "never"
    if capture in ("never", "start", "end", "both"):
        return capture  # type: ignore[return-value]
    return "end"


def _resolve_tap_pct(op: dict[str, Any]) -> list[float] | None:
    raw = op.get("tapPct") or op.get("tap_pct")
    if not isinstance(raw, list) or len(raw) != 2:
        return None
    return [float(raw[0]), float(raw[1])]


def _run_steps_operation(
    *,
    op: dict[str, Any],
    serial: str,
    account: dict[str, Any],
    shot_dir: Path,
    max_screenshots: int,
    op_start_time: int,
) -> dict[str, Any]:
    steps = op.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError(f"步骤 {op.get('step')} steps 须为非空数组")

    text_expr = op.get("textFrom") or op.get("text")
    text = _resolve_value(str(text_expr), account) if text_expr else None

    out = run_chain(
        serial=serial,
        steps=steps,
        capture=_resolve_capture_mode(op),
        screenshot_dir=shot_dir,
        max_screenshots=max_screenshots,
        use_adaptation=not bool(op.get("noAdapt")),
        text=text,
        popup_gate_auto=bool(op.get("popupGateAuto")),
    )
    attach_foreground_activity(serial=serial, result=out)
    tunnel_verify = _tunnel_verify_from_op(op, account=account, start_time=op_start_time)
    if tunnel_verify is not None:
        out["tunnelVerify"] = tunnel_verify
    tunnel_ok = True
    if isinstance(op.get("tunnel"), dict) and op["tunnel"].get("keyword"):
        tunnel_ok = bool(tunnel_verify and tunnel_verify.get("ok"))
    return out, tunnel_ok


def _run_operation(
    *,
    op: dict[str, Any],
    serial: str,
    account: dict[str, Any],
    shot_dir: Path,
    max_screenshots: int,
    force_script: bool,
) -> dict[str, Any]:
    action = str(op.get("action") or "").strip().lower()
    step_no = op.get("step")
    description = str(op.get("description") or action)
    op_start_time = int(time.time()) - 5

    if action == "account_check":
        alias = _resolve_value(str(op.get("account") or "account.alias"), account)
        since_seconds = int(op.get("sinceSeconds") or 300)
        check_result = check_account(account=alias, since_seconds=since_seconds)
        expect_in_use = op.get("expectInUse")
        in_use = bool(check_result.get("inUse"))
        if expect_in_use is None:
            ok = True
        else:
            ok = in_use is bool(expect_in_use)
        if op.get("optional") and not ok:
            ok = True
        return {
            "step": step_no,
            "action": action,
            "description": description,
            "ok": ok,
            "exitCode": 0 if ok else 3,
            "detail": check_result,
            "message": "账号状态符合预期" if ok else "账号状态不符合预期",
        }

    if action in ("steps", "chain"):
        detail, tunnel_ok = _run_steps_operation(
            op=op,
            serial=serial,
            account=account,
            shot_dir=shot_dir,
            max_screenshots=max_screenshots,
            op_start_time=op_start_time,
        )
        ok = tunnel_ok
        return {
            "step": step_no,
            "action": action,
            "description": description,
            "ok": ok,
            "exitCode": 0 if ok else 3,
            "detail": detail,
            "message": "内联步骤执行成功" if ok else "内联步骤或抓包验收失败",
        }

    if action == "tap":
        pct = _resolve_tap_pct(op)
        tap_x = op.get("x")
        tap_y = op.get("y")
        if pct is not None:
            width, height = display_size(serial)
            tap_x = int(pct[0] * width)
            tap_y = int(pct[1] * height)
        if tap_x is None or tap_y is None:
            raise ValueError(f"步骤 {step_no} tap 需要 x/y 或 tapPct/tap_pct")
        tap(x=int(tap_x), y=int(tap_y), serial=serial)
        detail: dict[str, Any] = {"x": int(tap_x), "y": int(tap_y)}
        if pct is not None:
            detail["tapPct"] = pct
        attach_foreground_activity(serial=serial, result=detail)
        return {
            "step": step_no,
            "action": action,
            "description": description,
            "ok": True,
            "exitCode": 0,
            "detail": detail,
            "message": "点击成功",
        }

    if action == "swipe":
        sw = op.get("swipe")
        if not isinstance(sw, dict):
            raise ValueError(f"步骤 {step_no} swipe 需要 swipe 对象")
        swipe(
            x1=int(sw["x1"]),
            y1=int(sw["y1"]),
            x2=int(sw["x2"]),
            y2=int(sw["y2"]),
            duration_ms=int(sw.get("duration_ms") or sw.get("durationMs") or 300),
            serial=serial,
        )
        detail = {"swipe": sw}
        attach_foreground_activity(serial=serial, result=detail)
        return {
            "step": step_no,
            "action": action,
            "description": description,
            "ok": True,
            "exitCode": 0,
            "detail": detail,
            "message": "滑动成功",
        }

    if action == "sleep":
        if op.get("seconds") is not None:
            ms = int(float(op["seconds"]) * 1000)
        else:
            ms = int(op.get("sleepMs") or op.get("sleep_ms") or 0)
        if ms > 0:
            time.sleep(ms / 1000.0)
        return {
            "step": step_no,
            "action": action,
            "description": description,
            "ok": True,
            "exitCode": 0,
            "detail": {"sleepMs": ms},
            "message": f"等待 {ms}ms",
        }

    if action == "text":
        content = _resolve_value(str(op.get("textFrom") or op.get("text") or ""), account)
        if not content:
            raise ValueError(f"步骤 {step_no} text 内容为空")
        input_text(text=content, serial=serial, clear_first=not op.get("noClear"))
        return {
            "step": step_no,
            "action": action,
            "description": description,
            "ok": True,
            "exitCode": 0,
            "detail": {"text": content},
            "message": "输入成功",
        }

    if action == "key":
        code = int(op.get("code") or op.get("key"))
        keyevent(code=code, serial=serial)
        return {
            "step": step_no,
            "action": action,
            "description": description,
            "ok": True,
            "exitCode": 0,
            "detail": {"key": code},
            "message": "按键成功",
        }

    if action == "capture":
        cap = capture_screenshot(
            serial=serial,
            directory=shot_dir,
            max_keep=max_screenshots,
        )
        return {
            "step": step_no,
            "action": action,
            "description": description,
            "ok": True,
            "exitCode": 0,
            "detail": {"screenshot": cap},
            "message": "截图成功",
        }

    if action == "macro":
        script = str(op.get("script") or "").strip()
        if not script:
            raise ValueError(f"步骤 {step_no} macro 缺少 script")
        assert_fragment_script_allowed(script, force_script=force_script)

        text_expr = op.get("textFrom") or op.get("text")
        text = _resolve_value(str(text_expr), account) if text_expr else None

        tunnel = op.get("tunnel") if isinstance(op.get("tunnel"), dict) else {}
        tunnel_account = _resolve_value(
            str(tunnel.get("account") or "account.alias"),
            account,
        )
        popup_scene = op.get("popupScene")
        result, exit_code = run_macro_command(
            args=_make_macro_args(
                serial=serial,
                script=script,
                text=text or None,
                shot_dir=shot_dir,
                max_screenshots=max_screenshots,
                tunnel_account=tunnel_account or str(account.get("alias") or ""),
                tunnel_keyword=str(tunnel.get("keyword") or "").strip() or None,
                tunnel_wait=int(tunnel.get("waitSeconds") or 30),
                tunnel_expect_ec=int(tunnel["expectEc"]) if tunnel.get("expectEc") is not None else 200,
                popup_scene=str(popup_scene) if popup_scene else None,
                popup_auto_dismiss=bool(op.get("popupAutoDismiss")),
                no_capture=bool(op.get("noCapture")),
                force_script=force_script,
            ),
            serial=serial,
            shot_dir=shot_dir,
        )
        attach_foreground_activity(serial=serial, result=result)
        tunnel_verify = result.get("tunnelVerify")
        tunnel_ok = True
        if isinstance(tunnel, dict) and tunnel.get("keyword"):
            tunnel_ok = isinstance(tunnel_verify, dict) and bool(tunnel_verify.get("ok"))
        ok = exit_code == 0 and tunnel_ok
        return {
            "step": step_no,
            "action": action,
            "description": description,
            "script": script,
            "text": text,
            "ok": ok,
            "exitCode": exit_code,
            "detail": result,
            "message": "操作成功" if ok else "操作或抓包验收失败",
        }

    raise ValueError(
        f"未知操作 action={action!r}（步骤 {step_no}）；"
        "支持: account_check / macro / steps / chain / tap / swipe / sleep / text / key / capture"
    )


def execute_case(
    *,
    case_id: str,
    serial: str,
    shot_dir: Path,
    max_screenshots: int = 10,
    force_script: bool = False,
) -> dict[str, Any]:
    case = load_case(case_id)
    account = case["_resolvedAccount"]
    operations = case.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValueError(f"用例 {case_id} 缺少 operations")

    start_time = int(time.time()) - 5
    operation_results: list[dict[str, Any]] = []
    last_screenshot: dict[str, Any] | None = None
    failed = False

    for raw_op in operations:
        if not isinstance(raw_op, dict):
            continue
        op_result = _run_operation(
            op=raw_op,
            serial=serial,
            account=account,
            shot_dir=shot_dir,
            max_screenshots=max_screenshots,
            force_script=force_script,
        )
        detail = op_result.get("detail")
        if isinstance(detail, dict):
            shot = detail.get("screenshot")
            if isinstance(shot, dict):
                last_screenshot = shot
        operation_results.append(op_result)
        if not op_result.get("ok"):
            failed = True
            if case.get("stopOnFailure", True):
                break

    ops_failed = failed
    verify_results: list[dict[str, Any]] = []
    verify_points = case.get("verifyPoints")
    if isinstance(verify_points, list):
        for raw_vp in verify_points:
            if not isinstance(raw_vp, dict):
                continue
            if ops_failed and case.get("skipVerifyOnFailure", True):
                verify_results.append(
                    {
                        "id": raw_vp.get("id"),
                        "name": raw_vp.get("name"),
                        "method": raw_vp.get("method"),
                        "ok": False,
                        "skipped": True,
                        "message": "前置操作步骤失败，跳过本验收点",
                    }
                )
                continue
            vp_result = run_verify_point(
                spec=raw_vp,
                serial=serial,
                account=account,
                screenshot_dir=shot_dir,
                max_screenshots=max_screenshots,
                start_time=start_time,
                last_screenshot=last_screenshot,
            )
            verify_results.append(vp_result)
            if not vp_result.get("ok"):
                failed = True

    passed = not failed and all(r.get("ok") for r in verify_results)
    return {
        "caseId": case_id,
        "name": case.get("name"),
        "priority": case.get("priority", "P0"),
        "module": case.get("module"),
        "source": case.get("source"),
        "account": account,
        "operationFlow": [
            {
                "step": r.get("step"),
                "description": r.get("description"),
                "action": r.get("action"),
                "script": r.get("script"),
                "ok": r.get("ok"),
                "message": r.get("message"),
            }
            for r in operation_results
        ],
        "operations": operation_results,
        "verifyPoints": verify_results,
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "startedAt": start_time,
        "finishedAt": int(time.time()),
    }


def execute_suite(
    *,
    case_ids: list[str],
    serial: str,
    shot_dir: Path,
    max_screenshots: int = 10,
    force_script: bool = False,
    suite_id: str | None = None,
    suite_name: str | None = None,
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for case_id in case_ids:
        cases.append(
            execute_case(
                case_id=case_id,
                serial=serial,
                shot_dir=shot_dir,
                max_screenshots=max_screenshots,
                force_script=force_script,
            )
        )

    passed_count = sum(1 for c in cases if c.get("passed"))
    return {
        "suiteId": suite_id,
        "suiteName": suite_name,
        "caseCount": len(cases),
        "passedCount": passed_count,
        "failedCount": len(cases) - passed_count,
        "passed": passed_count == len(cases) and len(cases) > 0,
        "status": "PASS" if passed_count == len(cases) and cases else "FAIL",
        "cases": cases,
        "finishedAt": int(time.time()),
    }
