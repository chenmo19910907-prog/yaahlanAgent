#!/usr/bin/env python3
"""无线 ADB 整屏截图 MCP 服务。"""

from __future__ import annotations

import base64
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import ImageContent, TextContent, Tool

REPO_ROOT = Path(__file__).resolve().parents[4]
ADB_PKG = REPO_ROOT / "AdbScreenshot"
if str(ADB_PKG) not in sys.path:
    sys.path.insert(0, str(ADB_PKG))

from adb.cli import main as cli_main  # noqa: E402
from adb.env import load_local_env  # noqa: E402

load_local_env(str(ADB_PKG))

server = Server("adb-screenshot")


def _capture_cli(args: list[str]) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = cli_main(args)
    return exit_code, stdout.getvalue().strip(), stderr.getvalue().strip()


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_wireless_devices",
            description="列出 wireless_devices.json 中登记的测试机及无线 adb 地址",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        Tool(
            name="adb_devices",
            description="执行 adb devices，查看当前已连接设备",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        Tool(
            name="connect_wireless",
            description="adb connect 无线地址（host:port）",
            inputSchema={
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "无线 adb 地址，如 192.168.1.100:5555"},
                },
                "required": ["address"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="screenshot",
            description=(
                "通过无线 ADB 截取 Android 手机整屏。可提供 asset_id、mmuid/mmuidv3、"
                "wireless 地址或设备名称之一。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string", "description": "资产编号"},
                    "mmuid": {"type": "string", "description": "mmuid 或 mmuidv3"},
                    "address": {"type": "string", "description": "无线 adb 地址 host:port"},
                    "name": {"type": "string", "description": "设备名称模糊匹配"},
                    "skip_connect": {
                        "type": "boolean",
                        "description": "为 true 时跳过 adb connect",
                        "default": False,
                    },
                },
                "additionalProperties": False,
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent | ImageContent]:
    if name == "list_wireless_devices":
        exit_code, output, error_output = _capture_cli(["--list-registry", "--json"])
        if exit_code != 0:
            payload = {"ok": False, "error": error_output or output or "读取登记表失败"}
            return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]
        return [TextContent(type="text", text=output)]

    if name == "adb_devices":
        from adb.client import list_devices

        devices = [{"serial": item.serial, "state": item.state} for item in list_devices()]
        return [TextContent(type="text", text=json.dumps(devices, ensure_ascii=False, indent=2))]

    if name == "connect_wireless":
        address = str(arguments.get("address") or "").strip()
        if not address:
            return [TextContent(type="text", text=json.dumps({"ok": False, "error": "缺少 address"}, ensure_ascii=False))]
        from adb.client import connect_wireless

        message = connect_wireless(address)
        payload = {"ok": True, "message": message, "address": address}
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]

    if name == "screenshot":
        args = ["--screenshot", "--json"]
        for key in ("asset_id", "mmuid", "address", "name"):
            value = arguments.get(key)
            if value:
                flag = {
                    "asset_id": "--asset",
                    "mmuid": "--mmuid",
                    "address": "--address",
                    "name": "--name",
                }[key]
                args.extend([flag, str(value)])
        if arguments.get("skip_connect"):
            args.append("--skip-connect")

        if "--asset" not in args and "--mmuid" not in args and "--address" not in args and "--name" not in args:
            payload = {"ok": False, "error": "请提供 asset_id、mmuid、address 或 name 之一"}
            return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]

        exit_code, output, error_output = _capture_cli(args)

        if exit_code != 0:
            payload = {"ok": False, "error": error_output or output or "截图失败"}
            return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]

        try:
            result = json.loads(output)
        except json.JSONDecodeError:
            return [TextContent(type="text", text=output or error_output)]

        image_path = result.get("output_path")
        contents: list[TextContent | ImageContent] = [
            TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))
        ]
        if image_path and os.path.isfile(image_path):
            with open(image_path, "rb") as handle:
                encoded = base64.b64encode(handle.read()).decode("ascii")
            contents.append(ImageContent(type="image", data=encoded, mimeType="image/png"))
        return contents

    return [TextContent(type="text", text=json.dumps({"ok": False, "error": f"未知工具: {name}"}, ensure_ascii=False))]


async def _main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(_main())
