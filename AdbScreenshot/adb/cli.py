"""无线 ADB 截图 CLI。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

from .client import AdbError, capture_screen, connect_wireless, disconnect_wireless, list_devices
from .config import default_screenshot_dir, default_wireless_registry_path, package_dir
from .env import load_local_env
from .registry import find_wireless_device, load_wireless_devices


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="通过无线 ADB 截取 Android 手机整屏（系统级 screencap）"
    )
    parser.add_argument(
        "--registry",
        default=os.environ.get("ADB_WIRELESS_REGISTRY"),
        help=f"无线设备登记表路径（默认 {default_wireless_registry_path()}）",
    )

    action = parser.add_mutually_exclusive_group()
    action.add_argument("--list-registry", action="store_true", help="列出无线设备登记表")
    action.add_argument("--adb-devices", action="store_true", help="列出当前 adb devices")
    action.add_argument("--connect", metavar="HOST:PORT", help="adb connect 无线地址")
    action.add_argument("--disconnect", nargs="?", const="", metavar="HOST:PORT", help="adb disconnect")
    action.add_argument("--screenshot", action="store_true", help="截取当前手机整屏")

    parser.add_argument("--address", help="无线地址 host:port，如 192.168.1.100:5555")
    parser.add_argument("--asset", help="资产编号，如 GZ3025010018")
    parser.add_argument("--mmuid", help="mmuid 或 mmuidv3")
    parser.add_argument("--name", help="设备名称模糊匹配")
    parser.add_argument(
        "--output",
        help="截图保存路径（默认 ~/Desktop/adb-screenshots/{标识}_{时间}.png）",
    )
    parser.add_argument("--skip-connect", action="store_true", help="跳过 adb connect（设备已连接时）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    return parser


def _print_registry(registry_path: str | None) -> int:
    devices = load_wireless_devices(registry_path)
    payload = {
        "registry_path": os.path.expanduser(registry_path or default_wireless_registry_path()),
        "devices": [
            {
                "asset_id": item.asset_id,
                "name": item.name,
                "wireless": item.wireless,
                "mmuid": item.mmuid,
                "mmuidv3": item.mmuidv3,
                "serial": item.serial,
                "note": item.note,
            }
            for item in devices
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _print_adb_devices() -> int:
    devices = list_devices()
    payload = [{"serial": item.serial, "state": item.state} for item in devices]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _default_output_path(label: str) -> str:
    screenshot_dir = default_screenshot_dir()
    os.makedirs(screenshot_dir, exist_ok=True)
    safe_label = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label) or "device"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(screenshot_dir, f"{safe_label}_{timestamp}.png")


def _resolve_target(args: argparse.Namespace):
    if args.address:
        return find_wireless_device(devices=[], address=args.address), "address"

    devices = load_wireless_devices(args.registry)
    if args.asset:
        return find_wireless_device(devices=devices, asset_id=args.asset), "asset"
    if args.mmuid:
        return find_wireless_device(devices=devices, mmuid=args.mmuid), "mmuid"
    if args.name:
        return find_wireless_device(devices=devices, name_query=args.name), "name"

    raise ValueError("截屏需要 --address、--asset、--mmuid 或 --name 之一")


def _take_screenshot(args: argparse.Namespace) -> int:
    device, lookup = _resolve_target(args)
    serial = device.resolved_serial()
    if not serial:
        raise ValueError("目标设备未配置 wireless 或 serial")

    connect_message = ""
    if not args.skip_connect and device.wireless:
        connect_message = connect_wireless(device.wireless)
        serial = device.resolved_serial()

    png_bytes = capture_screen(serial)

    label = device.asset_id or device.name or lookup
    output_path = os.path.abspath(args.output or _default_output_path(label))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as handle:
        handle.write(png_bytes)

    payload = {
        "ok": True,
        "lookup": lookup,
        "asset_id": device.asset_id,
        "name": device.name,
        "serial": serial,
        "wireless": device.wireless,
        "connect_message": connect_message,
        "output_path": output_path,
        "size_bytes": len(png_bytes),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    load_local_env(package_dir())
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.list_registry:
            return _print_registry(args.registry)
        if args.adb_devices:
            return _print_adb_devices()
        if args.connect:
            message = connect_wireless(args.connect)
            payload = {"ok": True, "message": message, "serial": args.connect}
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        if args.disconnect is not None:
            target = args.disconnect or None
            message = disconnect_wireless(target)
            payload = {"ok": True, "message": message}
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        if args.screenshot:
            return _take_screenshot(args)

        parser.print_help()
        return 2
    except (AdbError, ValueError, OSError) as exc:
        payload = {"ok": False, "error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
