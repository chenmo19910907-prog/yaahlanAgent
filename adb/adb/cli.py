"""ADB 截图视觉循环 CLI。"""

from __future__ import annotations

import argparse
import json
import sys
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
            capture = _resolve_capture_mode(
                explicit=args.capture,
                no_capture=args.no_capture,
                default=spec.get("capture", "end"),
            )
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
            _emit(out)
            return 0

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
            capture = _resolve_capture_mode(
                explicit=args.capture,
                no_capture=args.no_capture,
                default=str(spec.get("capture", "end")),
            )
            out = run_compose(
                name=args.name,
                serial=serial,
                screenshot_dir=shot_dir,
                max_screenshots=args.max_screenshots,
                text=args.text,
                skip=set(args.skip),
                capture=capture,  # type: ignore[arg-type]
                verify_end=args.verify,
                use_adaptation=_use_adaptation(args),
            )
            _emit(out)
            return 0

        if args.command == "chain":
            steps, file_capture = load_steps_file(args.steps_file)
            capture = _resolve_capture_mode(
                explicit=args.capture,
                no_capture=args.no_capture,
                default=file_capture,
            )
            out = run_chain(
                serial=serial,
                steps=steps,
                capture=capture,
                screenshot_dir=shot_dir,
                max_screenshots=args.max_screenshots,
                use_adaptation=_use_adaptation(args),
            )
            out["stepsFile"] = str(args.steps_file.resolve())
            _emit(out)
            return 0

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
