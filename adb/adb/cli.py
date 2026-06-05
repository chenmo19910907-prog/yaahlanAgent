"""ADB 截图视觉循环 CLI。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .actions import input_text, keyevent, swipe, tap
from .chain import load_steps_file, run_chain
from .device import AdbError, display_size, list_devices, require_device
from .device_calibrate import (
    calibrate_commit,
    calibrate_init,
    calibrate_set_point,
    device_info_payload,
    profile_show,
    record_reference_device,
)
from .device_profile import (
    adapt_dir,
    default_draft_path,
    list_profile_paths,
    load_profile,
)
from .compose import load_compose, list_compose_summary, run_compose
from .macros import apply_skip_flags, list_macros, resolve_macro
from .recorded_scripts import (
    list_catalog,
    list_composes_by_module,
    list_fragments_by_module,
    scripts_root,
)
from .screenshot import (
    DEFAULT_MAX_SCREENSHOTS,
    capture_screenshot,
    latest_screenshot,
    png_dimensions,
    screenshot_dir,
)
from .gift_panel_analyze import analyze_gift_panel_from_tunnel, find_gifts_from_tunnel
from .popup_analyze import analyze_scene_from_tunnel
from .tunnel_verify import (
    TunnelVerifyOptions,
    add_tunnel_arguments,
    attach_tunnel_verify,
    resolve_momoid,
    tunnel_options_from_args,
    wait_for_tunnel,
)


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "ADB 截图视觉循环：确定路径用 chain/macro 连续操作，仅在边界 capture；"
            f"不确定时再读图。目录内仅保留最新 {DEFAULT_MAX_SCREENSHOTS} 张 PNG"
        ),
    )
    parser.add_argument("--serial", "-s", help="设备 serial（多台时必须指定）")
    parser.add_argument(
        "--screenshot-dir",
        help=f"截图目录（默认 adb/screenshots/）",
    )
    parser.add_argument(
        "--max-screenshots",
        type=int,
        default=DEFAULT_MAX_SCREENSHOTS,
        help=f"最多保留截图数量（默认 {DEFAULT_MAX_SCREENSHOTS}）",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="列出已连接设备")

    p_cap = sub.add_parser("capture", help="截屏并 prune 旧图（视觉循环第一步）")
    p_cap.add_argument(
        "--no-json",
        action="store_true",
        help="仅打印截图路径（默认输出 JSON 含宽高与保留列表）",
    )

    p_latest = sub.add_parser("latest", help="输出最新截图路径（若无则 exit 2）")

    p_info = sub.add_parser("info", help="设备屏幕尺寸 + 最新截图信息")

    p_tap = sub.add_parser("tap", help="点击坐标（视觉循环：读图后算出的 x y）")
    p_tap.add_argument("x", type=int)
    p_tap.add_argument("y", type=int)

    p_swipe = sub.add_parser("swipe", help="滑动")
    p_swipe.add_argument("x1", type=int)
    p_swipe.add_argument("y1", type=int)
    p_swipe.add_argument("x2", type=int)
    p_swipe.add_argument("y2", type=int)
    p_swipe.add_argument("--duration", type=int, default=300, help="毫秒")

    p_key = sub.add_parser("key", help="按键（如 4=BACK 3=HOME）")
    p_key.add_argument("code", type=int)

    p_text = sub.add_parser("text", help="输入文本")
    p_text.add_argument("content")

    p_cycle = sub.add_parser(
        "cycle",
        help="一步循环：先截屏（返回路径供读图），你 tap 后再执行 capture 或单独 capture",
    )

    p_scripts = sub.add_parser(
        "scripts",
        help="列出 adb/录制脚本 片段目录",
    )

    p_macros = sub.add_parser("macros", help="列出录制片段（同 scripts 中 kind=fragment）")

    p_macro = sub.add_parser("macro", help="执行录制片段（支持中文名）")
    p_macro.add_argument("name", help="中文名或 id，如 发布纯文本动态")
    p_macro.add_argument(
        "--skip",
        action="append",
        default=[],
        metavar="KEY",
        help="跳过带 skip_key 的步骤，如 dismiss_popup_taps、dismiss_splash_ad、login_lang",
    )
    p_macro.add_argument(
        "--text",
        help="片段参数：发布纯文本动态 的正文（纯文本，建议数字/英文）",
    )
    p_macro.add_argument(
        "--capture",
        choices=("never", "start", "end", "both"),
        help="覆盖宏内 capture 策略",
    )
    p_macro.add_argument(
        "--no-capture",
        action="store_true",
        help="等同 --capture never，全程不截图（最连贯）",
    )
    p_macro.add_argument(
        "--no-adapt",
        action="store_true",
        help="跳过设备换算（仅调试用；换机未校准时不要用）",
    )
    add_tunnel_arguments(p_macro)

    p_chain = sub.add_parser(
        "chain",
        help="按步骤文件连续操作（默认结束时 capture 一次）",
    )
    p_chain.add_argument(
        "steps_file",
        type=Path,
        help="JSON：{ \"capture\": \"end\", \"steps\": [...] }",
    )
    p_chain.add_argument(
        "--capture",
        choices=("never", "start", "end", "both"),
        help="覆盖文件中的 capture",
    )
    p_chain.add_argument(
        "--no-capture",
        action="store_true",
        help="等同 --capture never",
    )
    p_chain.add_argument("--no-adapt", action="store_true", help="跳过设备换算")
    add_tunnel_arguments(p_chain)

    p_device = sub.add_parser("device", help="设备型号与坐标换算（换机先校准）")
    dev_sub = p_device.add_subparsers(dest="device_command", required=True)
    dev_sub.add_parser("info", help="当前设备型号、分辨率、是否已有换算档案")

    p_dev_prof = dev_sub.add_parser("profiles", help="列出已保存的设备档案")
    p_dev_init = dev_sub.add_parser(
        "calibrate",
        help="从录制脚本提取基准点并截屏，生成校准草稿",
    )
    p_dev_init.add_argument(
        "--script",
        required=True,
        help="录制片段中文名或 id，如 发布纯文本动态",
    )
    p_dev_init.add_argument("--draft", type=Path, help="草稿 JSON 路径")
    p_dev_init.add_argument(
        "--force",
        action="store_true",
        help="已有档案时仍重新截图校准（用于操作失败后更正）",
    )

    p_dev_recal = dev_sub.add_parser(
        "recalibrate",
        help="等同 calibrate --force（更正已有机型的换算）",
    )
    p_dev_recal.add_argument("--script", required=True)
    p_dev_recal.add_argument("--draft", type=Path)

    p_dev_set = dev_sub.add_parser(
        "set",
        help="根据截图读到的像素填写某校准点的 devicePct",
    )
    p_dev_set.add_argument("--draft", type=Path, help="草稿路径（默认按 serial）")
    p_dev_set.add_argument("--note", required=True, help="与草稿 anchor.note 对应")
    p_dev_set.add_argument("--device-pct", nargs=2, type=float, metavar=("X", "Y"))
    p_dev_set.add_argument("--pixel", nargs=2, type=int, metavar=("X", "Y"))

    p_dev_commit = dev_sub.add_parser(
        "commit",
        help="根据草稿拟合换算并写入设备档案",
    )
    p_dev_commit.add_argument("--draft", type=Path)
    p_dev_commit.add_argument("--id", required=True, dest="profile_id", help="档案 id")
    p_dev_commit.add_argument("--name", required=True, help="档案中文名")
    p_dev_commit.add_argument(
        "--fix-offset",
        action="store_true",
        help="仅缩放、offset=0（校准点少时用）",
    )
    p_dev_commit.add_argument(
        "--reason",
        choices=("initial", "correction"),
        default="initial",
        help="initial=首次建档；correction=操作失败后更正",
    )

    dev_sub.add_parser(
        "record-reference",
        help="把当前手机记入基准设备.json（在录制基准机上执行一次）",
    )
    p_dev_show = dev_sub.add_parser("show", help="查看某档案详情")
    p_dev_show.add_argument("profile_id", help="档案 id")

    p_compose_list = sub.add_parser(
        "composes",
        help="列出组合搭建方案（按模块分子目录）",
    )

    p_compose = sub.add_parser(
        "compose",
        help="按顺序执行多个片段（积木搭建）",
    )
    p_compose.add_argument("name", help="组合中文名或文件名（无 .json）")
    p_compose.add_argument("--text", help="传给带 params.text 的片段")
    p_compose.add_argument(
        "--skip",
        action="append",
        default=[],
        metavar="KEY",
        help="全局跳过 skip_key（各块可再在组合 JSON 里单独 skip）",
    )
    p_compose.add_argument(
        "--capture",
        choices=("never", "start", "end", "both"),
        help="覆盖组合内 capture（默认取组合文件）",
    )
    p_compose.add_argument("--no-capture", action="store_true", help="等同 --capture never")
    p_compose.add_argument(
        "--verify",
        action="store_true",
        help="最后一块结束时截一张图核对",
    )
    p_compose.add_argument("--no-adapt", action="store_true", help="跳过设备换算")
    add_tunnel_arguments(p_compose)

    p_run = sub.add_parser(
        "run",
        help="自动化执行：ADB 操作 + 结束截图 + Tunnel 抓包校验（推荐 Agent 使用）",
    )
    run_src = p_run.add_mutually_exclusive_group(required=True)
    run_src.add_argument("--compose", metavar="NAME", help="执行组合")
    run_src.add_argument("--macro", metavar="NAME", help="执行片段")
    run_src.add_argument("--chain", type=Path, metavar="FILE", help="执行 chain JSON")
    p_run.add_argument("--text", help="片段/组合文本参数")
    p_run.add_argument(
        "--skip",
        action="append",
        default=[],
        metavar="KEY",
        help="跳过 skip_key",
    )
    p_run.add_argument(
        "--verify",
        action="store_true",
        help="结束时强制截图（tunnel 校验时默认也会截图）",
    )
    p_run.add_argument("--no-adapt", action="store_true", help="跳过设备换算")
    p_run.add_argument(
        "--popup-scene",
        choices=("login", "home", "me", "room", "mic"),
        help="操作后按场景分析 Tunnel 弹窗信号并给出处置建议",
    )
    p_run.add_argument(
        "--popup-auto-dismiss",
        action="store_true",
        help="popup 分析建议关弹窗时自动执行 dismissScripts（默认仅建议）",
    )
    p_run.add_argument("--popup-since", type=int, default=120, help="弹窗分析回溯秒数")
    add_tunnel_arguments(p_run)

    p_popup = sub.add_parser(
        "popup",
        help="结合 Tunnel 抓包分析登录/首页/Me/进房/开麦等节点的弹窗风险",
    )
    popup_sub = p_popup.add_subparsers(dest="popup_command", required=True)
    p_popup_analyze = popup_sub.add_parser(
        "analyze",
        help="分析最近抓包中的弹窗信号（可配合截图读图）",
    )
    p_popup_analyze.add_argument(
        "--scene",
        required=True,
        choices=("login", "home", "me", "room", "mic"),
        help="操作场景",
    )
    p_popup_analyze.add_argument("--momoid", help="userId")
    p_popup_analyze.add_argument("--account", help="testAccounts 键名")
    p_popup_analyze.add_argument("--since", type=int, default=120, help="回溯秒数")
    p_popup_analyze.add_argument("--g-appid", default="All")
    p_popup_analyze.add_argument("--g-env", default="alpha")
    p_popup_analyze.add_argument(
        "--capture",
        action="store_true",
        help="分析后截一张图供 Agent 读图确认 weakUiPopups",
    )
    p_popup_analyze.add_argument(
        "--auto-dismiss",
        action="store_true",
        help="存在 actionable 信号时自动执行关闭常见弹窗等脚本",
    )
    p_popup_analyze.add_argument("--no-adapt", action="store_true")

    p_tunnel = sub.add_parser(
        "tunnel",
        help="仅 Tunnel 抓包等待/查询（不操作 UI；配合手动或上轮 run 使用）",
    )
    tunnel_sub = p_tunnel.add_subparsers(dest="tunnel_command", required=True)
    p_tunnel_wait = tunnel_sub.add_parser(
        "wait",
        help="轮询直到匹配 URL 关键字或超时",
    )
    p_tunnel_wait.add_argument("--momoid", help="userId")
    p_tunnel_wait.add_argument(
        "--account",
        help="索引 testAccounts 键名，如 familyLeader",
    )
    p_tunnel_wait.add_argument("--keyword", default="", help="URL 关键字")
    p_tunnel_wait.add_argument("--since", type=int, default=300, help="回溯秒数")
    p_tunnel_wait.add_argument("--wait", type=int, default=30, dest="tunnel_wait")
    p_tunnel_wait.add_argument("--poll-ms", type=int, default=2000, dest="tunnel_poll_ms")
    p_tunnel_wait.add_argument(
        "--expect-status",
        type=int,
        default=200,
        help="HTTP status；-1 不校验",
    )
    p_tunnel_wait.add_argument("--expect-ec", type=int, dest="tunnel_expect_ec")
    p_tunnel_wait.add_argument("--g-appid", default="All", dest="tunnel_g_appid")
    p_tunnel_wait.add_argument("--g-env", default="alpha", dest="tunnel_g_env")

    p_gift = sub.add_parser(
        "gift",
        help="礼物面板：Tunnel 抓包解析 Tab/礼物列表（getGiftTabListV3）",
    )
    gift_sub = p_gift.add_subparsers(dest="gift_command", required=True)
    p_gift_panel = gift_sub.add_parser(
        "panel",
        help="解析礼物面板抓包",
    )
    panel_sub = p_gift_panel.add_subparsers(dest="panel_command", required=True)
    p_panel_analyze = panel_sub.add_parser("analyze", help="列出各 Tab 与礼物数量/价位")
    p_panel_find = panel_sub.add_parser("find", help="按价格/Tab/名称查找礼物")
    for p in (p_panel_analyze, p_panel_find):
        p.add_argument("--momoid", help="userId")
        p.add_argument("--account", help="testAccounts 键名")
        p.add_argument("--since", type=int, default=300, help="回溯秒数")
        p.add_argument("--g-appid", default="All")
        p.add_argument("--g-env", default="alpha")
    p_panel_find.add_argument("--price", type=int, help="钻石价格，如 99")
    p_panel_find.add_argument("--tab", dest="tab_name", help="Tab 名称子串，如 Gift / nation")
    p_panel_find.add_argument("--name", dest="name_contains", help="礼物名称子串")

    return parser


def _use_adaptation(args: argparse.Namespace) -> bool:
    return not getattr(args, "no_adapt", False)


def _resolve_capture_mode(
    *,
    explicit: str | None,
    no_capture: bool,
    default: str,
) -> str:
    if no_capture:
        return "never"
    return explicit or default


def _ensure_end_screenshot(
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


def _run_dismiss_scripts(
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


def _attach_popup_analysis(
    *,
    args: argparse.Namespace,
    result: dict[str, object],
    serial: str,
    shot_dir: Path,
    max_screenshots: int,
    scene: str,
    auto_dismiss: bool,
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
        skip_key = str(analysis.get("dismissSkipWhenNoPopup", "dismiss_popup_taps"))
        skip_keys: set[str] = set()
        if not analysis.get("hasPopupSignals"):
            skip_keys.add(skip_key)
        dismiss_blocks = _run_dismiss_scripts(
            serial=serial,
            script_names=[str(x) for x in analysis["dismissScripts"]],
            shot_dir=shot_dir,
            max_screenshots=max_screenshots,
            skip_keys=skip_keys,
            use_adaptation=_use_adaptation(args),
        )

    if analysis.get("needScreenshot") or dismiss_blocks:
        _ensure_end_screenshot(
            serial=serial,
            result=result,
            shot_dir=shot_dir,
            max_screenshots=max_screenshots,
        )

    analysis["dismissExecuted"] = dismiss_blocks
    result["popupAnalysis"] = analysis


def _finalize_with_tunnel(
    *,
    args: argparse.Namespace,
    result: dict[str, object],
    serial: str,
    shot_dir: Path,
    max_screenshots: int,
    start_time: int,
    compose_spec: dict[str, object] | None = None,
) -> int:
    tunnel_opts = tunnel_options_from_args(
        args,
        compose_spec=compose_spec,  # type: ignore[arg-type]
    )
    if tunnel_opts is None:
        return 0

    _ensure_end_screenshot(
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    shot_dir = screenshot_dir(args.screenshot_dir)

    try:
        if args.command == "devices":
            devices = list_devices(ready_only=False)
            _emit(
                {
                    "devices": [
                        {"serial": d.serial, "state": d.state} for d in devices
                    ]
                }
            )
            return 0

        serial = require_device(args.serial)

        if args.command == "capture" or args.command == "cycle":
            result = capture_screenshot(
                serial=serial,
                directory=shot_dir,
                max_keep=args.max_screenshots,
            )
            if args.no_json:
                print(result["path"])
            else:
                _emit(result)
            return 0

        if args.command == "latest":
            path = latest_screenshot(shot_dir)
            if path is None:
                print("尚无截图，请先执行 capture", file=sys.stderr)
                return 2
            w, h = png_dimensions(path)
            _emit({"path": str(path.resolve()), "width": w, "height": h})
            return 0

        if args.command == "info":
            w, h = display_size(serial)
            path = latest_screenshot(shot_dir)
            payload: dict[str, object] = {
                "serial": serial,
                "displayWidth": w,
                "displayHeight": h,
                "screenshotDir": str(shot_dir.resolve()),
                "maxScreenshots": args.max_screenshots,
            }
            if path:
                pw, ph = png_dimensions(path)
                payload["latestScreenshot"] = {
                    "path": str(path.resolve()),
                    "width": pw,
                    "height": ph,
                }
            _emit(payload)
            return 0

        if args.command == "tap":
            tap(x=args.x, y=args.y, serial=serial)
            _emit({"action": "tap", "x": args.x, "y": args.y, "serial": serial})
            return 0

        if args.command == "swipe":
            swipe(
                x1=args.x1,
                y1=args.y1,
                x2=args.x2,
                y2=args.y2,
                duration_ms=args.duration,
                serial=serial,
            )
            _emit(
                {
                    "action": "swipe",
                    "from": [args.x1, args.y1],
                    "to": [args.x2, args.y2],
                    "durationMs": args.duration,
                    "serial": serial,
                }
            )
            return 0

        if args.command == "key":
            keyevent(code=args.code, serial=serial)
            _emit({"action": "keyevent", "code": args.code, "serial": serial})
            return 0

        if args.command == "text":
            input_text(text=args.content, serial=serial)
            _emit({"action": "text", "serial": serial})
            return 0

        if args.command == "scripts":
            catalog = [e for e in list_catalog() if e.get("kind") != "compose"]
            composes = [e for e in list_catalog() if e.get("kind") == "compose"]
            _emit(
                {
                    "root": str(scripts_root().resolve()),
                    "fragmentModules": list(list_fragments_by_module().keys()),
                    "fragmentsByModule": list_fragments_by_module(),
                    "fragments": catalog,
                    "composeModules": list(list_composes_by_module().keys()),
                    "composesByModule": list_composes_by_module(),
                    "composes": composes,
                    "catalog": list_catalog(),
                }
            )
            return 0

        if args.command == "macros":
            _emit({"macros": list_macros()})
            return 0

        if args.command == "macro":
            spec = resolve_macro(args.name, text=args.text)
            tunnel_opts = tunnel_options_from_args(args)
            since_buffer = tunnel_opts.since_buffer_seconds if tunnel_opts else 5
            start_time = int(time.time()) - since_buffer
            capture = _resolve_capture_mode(
                explicit=args.capture,
                no_capture=args.no_capture,
                default=spec.get("capture", "end"),
            )
            if tunnel_opts is not None and capture == "never":
                capture = "end"
            steps = apply_skip_flags(
                list(spec.get("steps", [])),
                skip=set(args.skip),
            )
            out = run_chain(
                serial=serial,
                steps=steps,
                capture=capture,
                screenshot_dir=shot_dir,
                max_screenshots=args.max_screenshots,
                use_adaptation=_use_adaptation(args),
                text=args.text,
                skip=set(args.skip),
            )
            out["script"] = spec.get("name", args.name)
            out["scriptId"] = spec.get("id", args.name)
            out["description"] = spec.get("description", "")
            if args.text is not None:
                out["text"] = args.text
            code = _finalize_with_tunnel(
                args=args,
                result=out,
                serial=serial,
                shot_dir=shot_dir,
                max_screenshots=args.max_screenshots,
                start_time=start_time,
            )
            _emit(out)
            return code

        if args.command == "composes":
            _emit(
                {
                    "composes": list_compose_summary(),
                    "composesByModule": list_composes_by_module(),
                    "root": str(scripts_root() / "组合"),
                }
            )
            return 0

        if args.command == "compose":
            spec = load_compose(args.name)
            tunnel_opts = tunnel_options_from_args(args, compose_spec=spec)
            since_buffer = tunnel_opts.since_buffer_seconds if tunnel_opts else 5
            start_time = int(time.time()) - since_buffer
            capture = _resolve_capture_mode(
                explicit=args.capture,
                no_capture=args.no_capture,
                default=str(spec.get("capture", "end")),
            )
            verify_end = args.verify or tunnel_opts is not None
            out = run_compose(
                name=args.name,
                serial=serial,
                screenshot_dir=shot_dir,
                max_screenshots=args.max_screenshots,
                text=args.text,
                skip=set(args.skip),
                capture=capture,  # type: ignore[arg-type]
                verify_end=verify_end,
                use_adaptation=_use_adaptation(args),
            )
            code = _finalize_with_tunnel(
                args=args,
                result=out,
                serial=serial,
                shot_dir=shot_dir,
                max_screenshots=args.max_screenshots,
                start_time=start_time,
                compose_spec=spec,
            )
            _emit(out)
            return code

        if args.command == "chain":
            steps, file_capture = load_steps_file(args.steps_file)
            tunnel_opts = tunnel_options_from_args(args)
            since_buffer = tunnel_opts.since_buffer_seconds if tunnel_opts else 5
            start_time = int(time.time()) - since_buffer
            capture = _resolve_capture_mode(
                explicit=args.capture,
                no_capture=args.no_capture,
                default=file_capture,
            )
            if tunnel_opts is not None and capture == "never":
                capture = "end"
            out = run_chain(
                serial=serial,
                steps=steps,
                capture=capture,
                screenshot_dir=shot_dir,
                max_screenshots=args.max_screenshots,
                use_adaptation=_use_adaptation(args),
            )
            out["stepsFile"] = str(args.steps_file.resolve())
            code = _finalize_with_tunnel(
                args=args,
                result=out,
                serial=serial,
                shot_dir=shot_dir,
                max_screenshots=args.max_screenshots,
                start_time=start_time,
            )
            _emit(out)
            return code

        if args.command == "run":
            tunnel_opts = tunnel_options_from_args(args)
            popup_scene = getattr(args, "popup_scene", None)
            if tunnel_opts is None and not popup_scene:
                raise ValueError(
                    "run 须指定 --tunnel-keyword，或指定 --popup-scene 做弹窗抓包分析"
                )
            if popup_scene and not (
                getattr(args, "tunnel_momoid", None) or getattr(args, "tunnel_account", None)
            ):
                raise ValueError("run 使用 --popup-scene 时须同时指定 --tunnel-account 或 --tunnel-momoid")
            since_buffer = tunnel_opts.since_buffer_seconds if tunnel_opts else 5
            start_time = int(time.time()) - since_buffer
            out: dict[str, object]
            compose_spec: dict[str, object] | None = None

            if args.compose:
                compose_spec = load_compose(args.compose)
                out = run_compose(
                    name=args.compose,
                    serial=serial,
                    screenshot_dir=shot_dir,
                    max_screenshots=args.max_screenshots,
                    text=args.text,
                    skip=set(args.skip),
                    capture="end",
                    verify_end=True,
                    use_adaptation=_use_adaptation(args),
                )
                out["runMode"] = "compose"
            elif args.macro:
                spec = resolve_macro(args.macro, text=args.text)
                steps = apply_skip_flags(
                    list(spec.get("steps", [])),
                    skip=set(args.skip),
                )
                out = run_chain(
                    serial=serial,
                    steps=steps,
                    capture="end",
                    screenshot_dir=shot_dir,
                    max_screenshots=args.max_screenshots,
                    use_adaptation=_use_adaptation(args),
                    text=args.text,
                    skip=set(args.skip),
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
                    use_adaptation=_use_adaptation(args),
                )
                out["runMode"] = "chain"
                out["stepsFile"] = str(args.chain.resolve())

            code = 0
            if tunnel_opts is not None:
                code = _finalize_with_tunnel(
                    args=args,
                    result=out,
                    serial=serial,
                    shot_dir=shot_dir,
                    max_screenshots=args.max_screenshots,
                    start_time=start_time,
                    compose_spec=compose_spec,
                )
            if popup_scene:
                _attach_popup_analysis(
                    args=args,
                    result=out,
                    serial=serial,
                    shot_dir=shot_dir,
                    max_screenshots=args.max_screenshots,
                    scene=popup_scene,
                    auto_dismiss=bool(getattr(args, "popup_auto_dismiss", False)),
                )
            _emit(out)
            return code

        if args.command == "popup":
            if args.popup_command == "analyze":
                if not getattr(args, "momoid", None) and not getattr(args, "account", None):
                    raise ValueError("popup analyze 须指定 --momoid 或 --account")
                momoid = resolve_momoid(
                    momoid=getattr(args, "momoid", None),
                    account=getattr(args, "account", None),
                )
                out: dict[str, object] = analyze_scene_from_tunnel(
                    momoid=momoid,
                    scene=args.scene,
                    since_seconds=int(args.since),
                    g_appid=str(args.g_appid),
                    g_env=str(args.g_env),
                )
                dismiss_blocks: list[dict[str, object]] = []
                if args.auto_dismiss and out.get("dismissScripts"):
                    skip_key = str(out.get("dismissSkipWhenNoPopup", "dismiss_popup_taps"))
                    skip_keys: set[str] = set()
                    if not out.get("hasPopupSignals"):
                        skip_keys.add(skip_key)
                    dismiss_blocks = _run_dismiss_scripts(
                        serial=serial,
                        script_names=[str(x) for x in out["dismissScripts"]],
                        shot_dir=shot_dir,
                        max_screenshots=args.max_screenshots,
                        skip_keys=skip_keys,
                        use_adaptation=_use_adaptation(args),
                    )
                    out["dismissExecuted"] = dismiss_blocks
                if args.capture or out.get("needScreenshot") or dismiss_blocks:
                    cap = capture_screenshot(
                        serial=serial,
                        directory=shot_dir,
                        max_keep=args.max_screenshots,
                    )
                    out["screenshot"] = cap
                _emit(out)
                return 0
            print(f"未知 popup 子命令: {args.popup_command}", file=sys.stderr)
            return 2

        if args.command == "gift":
            if not getattr(args, "momoid", None) and not getattr(args, "account", None):
                raise ValueError("gift panel 须指定 --momoid 或 --account")
            momoid = resolve_momoid(
                momoid=getattr(args, "momoid", None),
                account=getattr(args, "account", None),
            )
            if args.gift_command == "panel" and args.panel_command == "analyze":
                out = analyze_gift_panel_from_tunnel(
                    momoid=momoid,
                    since_seconds=int(args.since),
                    g_appid=str(args.g_appid),
                    g_env=str(args.g_env),
                )
                _emit(out)
                return 0
            if args.gift_command == "panel" and args.panel_command == "find":
                out = find_gifts_from_tunnel(
                    momoid=momoid,
                    since_seconds=int(args.since),
                    price=getattr(args, "price", None),
                    tab_name=getattr(args, "tab_name", None),
                    name_contains=getattr(args, "name_contains", None),
                    g_appid=str(args.g_appid),
                    g_env=str(args.g_env),
                )
                _emit(out)
                return 0 if out.get("matchedCount", 0) > 0 else 3
            print(f"未知 gift 子命令: {args.gift_command}", file=sys.stderr)
            return 2

        if args.command == "tunnel":
            if args.tunnel_command == "wait":
                if not getattr(args, "momoid", None) and not getattr(args, "account", None):
                    raise ValueError("tunnel wait 须指定 --momoid 或 --account")

                raw_status = args.expect_status
                http_status: int | None = None if raw_status < 0 else int(raw_status)
                opts = TunnelVerifyOptions(
                    momoid=resolve_momoid(
                        momoid=getattr(args, "momoid", None),
                        account=getattr(args, "account", None),
                    ),
                    keyword=str(args.keyword or ""),
                    wait_seconds=max(1, int(args.tunnel_wait)),
                    poll_interval_ms=max(500, int(args.tunnel_poll_ms)),
                    expect_http_status=http_status,
                    expect_response_ec=getattr(args, "tunnel_expect_ec", None),
                    since_buffer_seconds=0,
                    g_appid=str(args.tunnel_g_appid),
                    g_env=str(args.tunnel_g_env),
                )
                start_time = int(time.time()) - max(1, int(args.since))
                verify = wait_for_tunnel(opts, start_time=start_time)
                _emit({"tunnelVerify": verify})
                return 0 if verify.get("ok") else 3
            print(f"未知 tunnel 子命令: {args.tunnel_command}", file=sys.stderr)
            return 2

        if args.command == "device":
            if args.device_command == "info":
                _emit(device_info_payload(serial))
                return 0
            if args.device_command == "profiles":
                items = []
                for path in list_profile_paths():
                    try:
                        p = load_profile(path)
                    except (OSError, ValueError, json.JSONDecodeError):
                        continue
                    dev = p.get("device") or {}
                    items.append(
                        {
                            "id": p.get("id"),
                            "name": p.get("name"),
                            "deviceModel": p.get("deviceModel") or dev.get("model"),
                            "width": dev.get("width"),
                            "height": dev.get("height"),
                            "path": str(path.resolve()),
                            "reusePolicy": p.get("reusePolicy"),
                            "updatedAt": p.get("updatedAt"),
                            "transform": p.get("transform"),
                        }
                    )
                _emit({"adaptDir": str(adapt_dir().resolve()), "profiles": items})
                return 0
            draft = args.draft if getattr(args, "draft", None) else default_draft_path(serial)
            if args.device_command in ("calibrate", "recalibrate"):
                force = args.device_command == "recalibrate" or getattr(
                    args, "force", False
                )
                out = calibrate_init(
                    serial=serial,
                    script_key=args.script,
                    screenshot_dir=shot_dir,
                    max_screenshots=args.max_screenshots,
                    draft_path=draft,
                    force=force,
                )
                _emit(out)
                return 0
            if args.device_command == "record-reference":
                _emit(record_reference_device(serial))
                return 0
            if args.device_command == "show":
                _emit(profile_show(args.profile_id))
                return 0
            if args.device_command == "set":
                pct = None
                if args.device_pct:
                    pct = (float(args.device_pct[0]), float(args.device_pct[1]))
                pixel = None
                if args.pixel:
                    pixel = (int(args.pixel[0]), int(args.pixel[1]))
                out = calibrate_set_point(
                    draft_path=draft,
                    note=args.note,
                    device_pct=pct,
                    pixel=pixel,
                )
                _emit(out)
                return 0
            if args.device_command == "commit":
                out = calibrate_commit(
                    draft_path=draft,
                    profile_id=args.profile_id,
                    name=args.name,
                    fix_offset=args.fix_offset,
                    reason=args.reason,
                )
                _emit(out)
                return 0
            print(f"未知 device 子命令: {args.device_command}", file=sys.stderr)
            return 2

        print(f"未知命令: {args.command}", file=sys.stderr)
        return 2

    except (AdbError, ValueError, RuntimeError, OSError) as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
