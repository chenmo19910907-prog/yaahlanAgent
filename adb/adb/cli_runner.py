"""片段 / chain 执行器（macro、chain、run 共用）。"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any, Literal

from .ai_operate import assert_fragment_script_allowed, fragment_module
from .chain import load_steps_file, run_chain
from .cli_args import (
    apply_fast_tunnel_args,
    is_fast_mode,
    optional_momoid_from_args,
    popup_gate_auto_enabled,
    resolve_capture_mode,
    rtl_mode,
    use_adaptation,
)
from .cli_finalize import finalize_chain_execution, track_script_outcome
from .logcat_check import logcat_options_from_args
from .macros import apply_skip_flags, resolve_macro
from .screenshot import DEFAULT_CAPTURE_MAX_EDGE
from .tunnel_verify import tunnel_options_from_args

CaptureMode = Literal["never", "start", "end", "both"]


def _resolve_gate_momoid(args: argparse.Namespace) -> str | None:
    try:
        return optional_momoid_from_args(args)
    except ValueError:
        return None


def _resolve_capture_for_args(
    args: argparse.Namespace,
    *,
    default: str,
    tunnel_active: bool,
    logcat_active: bool,
) -> CaptureMode:
    capture = resolve_capture_mode(
        explicit=getattr(args, "capture", None),
        no_capture=bool(getattr(args, "no_capture", False)),
        default=default,
        fast=is_fast_mode(args),
    )
    if (tunnel_active or logcat_active) and capture == "never":
        return "end"
    return capture  # type: ignore[return-value]


def run_macro_command(
    *,
    args: argparse.Namespace,
    serial: str,
    shot_dir: Path,
) -> tuple[dict[str, object], int]:
    assert_fragment_script_allowed(
        args.name,
        force_script=bool(getattr(args, "force_script", False)),
    )
    spec = resolve_macro(args.name, text=args.text)
    apply_fast_tunnel_args(args)
    tunnel_opts = tunnel_options_from_args(args, script_spec=spec)
    logcat_opts = logcat_options_from_args(args, script_spec=spec)
    since_buffer = tunnel_opts.since_buffer_seconds if tunnel_opts else 5
    start_time = int(time.time()) - since_buffer
    capture = _resolve_capture_for_args(
        args,
        default=str(spec.get("capture", "end")),
        tunnel_active=tunnel_opts is not None,
        logcat_active=logcat_opts is not None,
    )
    steps = apply_skip_flags(list(spec.get("steps", [])), skip=set(args.skip))
    out = run_chain(
        serial=serial,
        steps=steps,
        capture=capture,
        screenshot_dir=shot_dir,
        max_screenshots=args.max_screenshots,
        use_adaptation=use_adaptation(args),
        text=args.text,
        skip=set(args.skip),
        popup_gate_auto=popup_gate_auto_enabled(args),
        popup_gate_momoid=_resolve_gate_momoid(args),
        capture_max_edge=getattr(args, "max_edge", DEFAULT_CAPTURE_MAX_EDGE),
        rtl_mode=rtl_mode(args),  # type: ignore[arg-type]
    )
    out["script"] = spec.get("name", args.name)
    out["scriptId"] = spec.get("id", args.name)
    out["description"] = spec.get("description", "")
    if args.text is not None:
        out["text"] = args.text

    code = finalize_chain_execution(
        args=args,
        result=out,
        serial=serial,
        shot_dir=shot_dir,
        max_screenshots=args.max_screenshots,
        start_time=start_time,
        script_spec=spec,
    )
    track_script_outcome(
        name=str(out.get("script", args.name)),
        kind="fragment",
        result=out,
        exit_code=code,
        module=fragment_module(args.name),
        script_id=str(out.get("scriptId", "")),
    )
    return out, code


def run_chain_command(
    *,
    args: argparse.Namespace,
    serial: str,
    shot_dir: Path,
) -> tuple[dict[str, object], int]:
    steps, file_capture = load_steps_file(args.steps_file)
    apply_fast_tunnel_args(args)
    tunnel_opts = tunnel_options_from_args(args)
    logcat_opts = logcat_options_from_args(args)
    since_buffer = tunnel_opts.since_buffer_seconds if tunnel_opts else 5
    start_time = int(time.time()) - since_buffer
    capture = _resolve_capture_for_args(
        args,
        default=file_capture,
        tunnel_active=tunnel_opts is not None,
        logcat_active=logcat_opts is not None,
    )
    out = run_chain(
        serial=serial,
        steps=steps,
        capture=capture,
        screenshot_dir=shot_dir,
        max_screenshots=args.max_screenshots,
        use_adaptation=use_adaptation(args),
        popup_gate_auto=popup_gate_auto_enabled(args),
        popup_gate_momoid=_resolve_gate_momoid(args),
        capture_max_edge=getattr(args, "max_edge", DEFAULT_CAPTURE_MAX_EDGE),
        rtl_mode=rtl_mode(args),  # type: ignore[arg-type]
    )
    out["stepsFile"] = str(args.steps_file.resolve())
    code = finalize_chain_execution(
        args=args,
        result=out,
        serial=serial,
        shot_dir=shot_dir,
        max_screenshots=args.max_screenshots,
        start_time=start_time,
    )
    return out, code


def run_integrated_command(
    *,
    args: argparse.Namespace,
    serial: str,
    shot_dir: Path,
) -> tuple[dict[str, object], int]:
    fragment_spec: dict[str, object] | None = None
    apply_fast_tunnel_args(args)
    tunnel_opts = tunnel_options_from_args(args)
    logcat_opts = logcat_options_from_args(args)
    popup_scene = getattr(args, "popup_scene", None)
    if tunnel_opts is None and not popup_scene and logcat_opts is None:
        raise ValueError("run 须指定 --tunnel-keyword、--logcat-grep 或 --popup-scene")
    if popup_scene and not (
        getattr(args, "tunnel_momoid", None) or getattr(args, "tunnel_account", None)
    ):
        raise ValueError(
            "run 使用 --popup-scene 时须同时指定 --tunnel-account 或 --tunnel-momoid"
        )
    since_buffer = tunnel_opts.since_buffer_seconds if tunnel_opts else 5
    start_time = int(time.time()) - since_buffer
    gate_momoid = _resolve_gate_momoid(args)

    if args.macro:
        assert_fragment_script_allowed(
            args.macro,
            force_script=bool(getattr(args, "force_script", False)),
        )
        spec = resolve_macro(args.macro, text=args.text)
        fragment_spec = spec
        steps = apply_skip_flags(list(spec.get("steps", [])), skip=set(args.skip))
        out: dict[str, object] = run_chain(
            serial=serial,
            steps=steps,
            capture="end",
            screenshot_dir=shot_dir,
            max_screenshots=args.max_screenshots,
            use_adaptation=use_adaptation(args),
            text=args.text,
            skip=set(args.skip),
            popup_gate_auto=popup_gate_auto_enabled(args),
            popup_gate_momoid=gate_momoid,
            capture_max_edge=getattr(args, "max_edge", DEFAULT_CAPTURE_MAX_EDGE),
            rtl_mode=rtl_mode(args),  # type: ignore[arg-type]
        )
        out["runMode"] = "macro"
        out["script"] = spec.get("name", args.macro)
    else:
        steps, _file_capture = load_steps_file(args.chain)
        out = run_chain(
            serial=serial,
            steps=steps,
            capture="end",
            screenshot_dir=shot_dir,
            max_screenshots=args.max_screenshots,
            use_adaptation=use_adaptation(args),
            popup_gate_auto=popup_gate_auto_enabled(args),
            popup_gate_momoid=gate_momoid,
            capture_max_edge=getattr(args, "max_edge", DEFAULT_CAPTURE_MAX_EDGE),
            rtl_mode=rtl_mode(args),  # type: ignore[arg-type]
        )
        out["runMode"] = "chain"
        out["stepsFile"] = str(args.chain.resolve())

    code = finalize_chain_execution(
        args=args,
        result=out,
        serial=serial,
        shot_dir=shot_dir,
        max_screenshots=args.max_screenshots,
        start_time=start_time,
        script_spec=fragment_spec,
        include_tunnel=tunnel_opts is not None,
    )
    if popup_scene:
        from .cli_finalize import attach_popup_analysis

        attach_popup_analysis(
            args=args,
            result=out,
            serial=serial,
            shot_dir=shot_dir,
            max_screenshots=args.max_screenshots,
            scene=popup_scene,
            auto_dismiss=bool(getattr(args, "popup_auto_dismiss", False)),
            use_adaptation=use_adaptation(args),
        )
    from .cli_finalize import attach_foreground_activity

    attach_foreground_activity(serial=serial, result=out)
    return out, code
