"""macro/chain/run 收尾：Tunnel、logcat、弹窗分析、脚本废弃追踪。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .activity import get_foreground_activity
from .chain import run_chain
from .logcat_check import attach_logcat_verify, logcat_options_from_args
from .macros import apply_skip_flags, resolve_macro
from .popup_analyze import analyze_scene_from_tunnel, dismiss_scripts_for_analysis
from .screenshot import capture_screenshot
from .script_abandon import failure_reason_from_result, record_script_run_outcome
from .tunnel_verify import attach_tunnel_verify, resolve_momoid, tunnel_options_from_args
from .verify.report import chain_result_exit_code


def ensure_end_screenshot(
    *,
    serial: str,
    result: dict[str, object],
    shot_dir: Path,
    max_screenshots: int,
) -> None:
    if result.get("screenshot"):
        return
    cap = capture_screenshot(
        serial=serial,
        directory=shot_dir,
        max_keep=max_screenshots,
    )
    result["screenshot"] = cap


def run_dismiss_scripts(
    *,
    serial: str,
    script_names: list[str],
    shot_dir: Path,
    max_screenshots: int,
    skip_keys: set[str],
    use_adaptation: bool,
) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    for name in script_names:
        frag = resolve_macro(name)
        steps = apply_skip_flags(list(frag.get("steps", [])), skip=skip_keys)
        out = run_chain(
            serial=serial,
            steps=steps,
            capture="never",
            screenshot_dir=shot_dir,
            max_screenshots=max_screenshots,
            use_adaptation=use_adaptation,
        )
        blocks.append(
            {
                "script": frag.get("name", name),
                "scriptId": frag.get("id", name),
                "stepsExecuted": out.get("stepsExecuted"),
            }
        )
    return blocks


def attach_popup_analysis(
    *,
    args: argparse.Namespace,
    result: dict[str, object],
    serial: str,
    shot_dir: Path,
    max_screenshots: int,
    scene: str,
    auto_dismiss: bool,
    use_adaptation: bool,
) -> None:
    momoid = resolve_momoid(
        momoid=getattr(args, "tunnel_momoid", None),
        account=getattr(args, "tunnel_account", None),
    )
    since_seconds = int(
        getattr(args, "popup_since", None) or getattr(args, "since", 120)
    )
    analysis = analyze_scene_from_tunnel(
        momoid=momoid,
        scene=scene,
        since_seconds=since_seconds,
        g_appid=str(getattr(args, "tunnel_g_appid", "All") or "All"),
        g_env=str(getattr(args, "tunnel_g_env", "alpha") or "alpha"),
    )

    dismiss_blocks: list[dict[str, object]] = []
    if auto_dismiss and analysis.get("dismissScripts"):
        dismiss_blocks = dismiss_scripts_for_analysis(
            serial=serial,
            analysis=analysis,  # type: ignore[arg-type]
            screenshot_dir=shot_dir,
            max_screenshots=max_screenshots,
            use_adaptation=use_adaptation,
        )

    if analysis.get("needScreenshot") or dismiss_blocks:
        ensure_end_screenshot(
            serial=serial,
            result=result,
            shot_dir=shot_dir,
            max_screenshots=max_screenshots,
        )

    analysis["dismissExecuted"] = dismiss_blocks
    result["popupAnalysis"] = analysis


def finalize_with_tunnel(
    *,
    args: argparse.Namespace,
    result: dict[str, object],
    serial: str,
    shot_dir: Path,
    max_screenshots: int,
    start_time: int,
    script_spec: dict[str, object] | None = None,
) -> int:
    tunnel_opts = tunnel_options_from_args(
        args,
        script_spec=script_spec,  # type: ignore[arg-type]
    )
    if tunnel_opts is None:
        return 0

    ensure_end_screenshot(
        serial=serial,
        result=result,
        shot_dir=shot_dir,
        max_screenshots=max_screenshots,
    )
    merged, ok = attach_tunnel_verify(
        result,  # type: ignore[arg-type]
        tunnel_opts,
        start_time=start_time,
    )
    result.clear()
    result.update(merged)
    return 0 if ok else 3


def finalize_with_logcat(
    *,
    args: argparse.Namespace,
    result: dict[str, object],
    serial: str,
    script_spec: dict[str, object] | None = None,
) -> int:
    logcat_opts = logcat_options_from_args(
        args,
        script_spec=script_spec,  # type: ignore[arg-type]
    )
    if logcat_opts is None:
        return 0
    merged, ok = attach_logcat_verify(
        result,  # type: ignore[arg-type]
        logcat_opts,
        serial=serial,
    )
    result.clear()
    result.update(merged)
    return 0 if ok else 3


def logcat_exit_code(result: dict[str, object]) -> int:
    verify = result.get("logcatVerify")
    if isinstance(verify, dict) and not verify.get("ok"):
        return 3
    if result.get("logcatVerifyFailed"):
        return 3
    return 0


def finalize_chain_execution(
    *,
    args: argparse.Namespace,
    result: dict[str, object],
    serial: str,
    shot_dir: Path,
    max_screenshots: int,
    start_time: int,
    script_spec: dict[str, object] | None = None,
    include_tunnel: bool = True,
    include_logcat: bool = True,
) -> int:
    """macro/chain/run 共用收尾。"""
    code = 0
    if include_tunnel:
        code = finalize_with_tunnel(
            args=args,
            result=result,
            serial=serial,
            shot_dir=shot_dir,
            max_screenshots=max_screenshots,
            start_time=start_time,
            script_spec=script_spec,
        )
    if include_logcat:
        code = max(
            code,
            finalize_with_logcat(
                args=args,
                result=result,
                serial=serial,
                script_spec=script_spec,
            ),
        )
    code = max(code, chain_result_exit_code(result), logcat_exit_code(result))
    attach_foreground_activity(serial=serial, result=result)
    return code


def attach_foreground_activity(*, serial: str, result: dict[str, object]) -> None:
    try:
        result["foregroundActivity"] = get_foreground_activity(serial=serial)
    except (RuntimeError, OSError, ValueError) as exc:
        result["foregroundActivity"] = {"ok": False, "error": str(exc)}


def track_script_outcome(
    *,
    name: str,
    kind: str,
    result: dict[str, object],
    exit_code: int,
    module: str | None = None,
    script_id: str | None = None,
) -> None:
    reason = failure_reason_from_result(result, exit_code)  # type: ignore[arg-type]
    track = record_script_run_outcome(
        name=name,
        kind=kind,
        ok=exit_code == 0,
        exit_code=exit_code,
        reason=None if exit_code == 0 else reason,
        module=module,
        script_id=script_id,
    )
    result["scriptFailureTrack"] = track
    if track.get("abandoned"):
        result["scriptAbandoned"] = True
        entry = track.get("entry")
        if isinstance(entry, dict) and entry.get("abandonReason"):
            result["agentHint"] = (
                f"{entry.get('abandonReason')}。"
                "该脚本已废弃，请 ai prepare + tunnel 抓包继续；"
                f"调试可用 ai restore {name} 或 --force-script。"
            )
