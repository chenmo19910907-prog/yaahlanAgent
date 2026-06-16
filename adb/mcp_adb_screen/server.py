#!/usr/bin/env python3
"""ADB 真机读屏 MCP Server — Cursor 直接调用 observe / activity / tap。"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import McpError
from mcp.types import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    ErrorData,
    ImageContent,
    TextContent,
    Tool,
)

# 仓库根 → adb 包
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADB_ROOT = _REPO_ROOT / "adb"
if str(_ADB_ROOT) not in sys.path:
    sys.path.insert(0, str(_ADB_ROOT))

from adb.actions import swipe, tap  # noqa: E402
from adb.activity import get_foreground_activity  # noqa: E402
from adb.device import AdbError, list_devices, require_device  # noqa: E402
from adb.screen_observe import observe_screen, wait_for_screen_change  # noqa: E402

server = Server("adb-screen")


def _resolve_serial(serial: str | None) -> str:
    return require_device(serial or None)


def _json_text(payload: Any) -> TextContent:
    return TextContent(
        type="text",
        text=json.dumps(payload, ensure_ascii=False, indent=2),
    )


def _observe_contents(payload: dict[str, Any], *, include_image: bool) -> list[TextContent | ImageContent]:
    out: list[TextContent | ImageContent] = [_json_text(payload)]
    if not include_image:
        return out
    screen = payload.get("screen") or {}
    path = screen.get("path")
    if not path:
        return out
    p = Path(str(path))
    if not p.is_file():
        return out
    out.append(
        ImageContent(
            type="image",
            data=base64.b64encode(p.read_bytes()).decode("ascii"),
            mimeType="image/png",
        )
    )
    return out


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="adb_devices",
            description="列出已连接 ADB 设备（serial / state）",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        Tool(
            name="adb_observe",
            description=(
                "读取手机屏幕：返回 Activity + ui.clickables（文本可分析）+ PNG 截图。"
                "原生页优先看 ui.clickables；WebView/图像页看附带截图。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "serial": {"type": "string", "description": "设备 serial，多台时必填"},
                    "includeImage": {
                        "type": "boolean",
                        "description": "是否附带 PNG（默认 false，原生页读 ui 树即可）",
                        "default": False,
                    },
                    "fast": {
                        "type": "boolean",
                        "description": "极速模式：仅 clickable 元素",
                        "default": True,
                    },
                    "maxEdge": {
                        "type": "integer",
                        "description": "截图最长边像素，默认 1170",
                        "default": 1170,
                    },
                    "uiLimit": {
                        "type": "integer",
                        "description": "ui.clickables 最大条数，默认 50",
                        "default": 50,
                    },
                },
                "additionalProperties": False,
            },
        ),
        Tool(
            name="adb_observe_wait",
            description=(
                "等待屏幕变化（Activity 或 UI 树变化）后返回 adb_observe 同样结构。"
                "用于 tap/macro 之后等界面稳定。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "serial": {"type": "string"},
                    "timeoutSec": {
                        "type": "number",
                        "description": "最长等待秒数，默认 12",
                        "default": 12,
                    },
                    "includeImage": {"type": "boolean", "default": False},
                    "fast": {"type": "boolean", "default": True},
                    "maxEdge": {"type": "integer", "default": 1170},
                    "uiLimit": {"type": "integer", "default": 50},
                },
                "additionalProperties": False,
            },
        ),
        Tool(
            name="adb_activity",
            description="仅查询当前前台 Activity（比 observe 快，无 UI 树/截图）",
            inputSchema={
                "type": "object",
                "properties": {
                    "serial": {"type": "string"},
                },
                "additionalProperties": False,
            },
        ),
        Tool(
            name="adb_tap",
            description="点击设备坐标（设备像素，非读图坐标）",
            inputSchema={
                "type": "object",
                "properties": {
                    "serial": {"type": "string"},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                "required": ["x", "y"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="adb_swipe",
            description="滑动（设备像素坐标）",
            inputSchema={
                "type": "object",
                "properties": {
                    "serial": {"type": "string"},
                    "x1": {"type": "integer"},
                    "y1": {"type": "integer"},
                    "x2": {"type": "integer"},
                    "y2": {"type": "integer"},
                    "durationMs": {"type": "integer", "default": 350},
                },
                "required": ["x1", "y1", "x2", "y2"],
                "additionalProperties": False,
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent | ImageContent]:
    try:
        if name == "adb_devices":
            devices = await asyncio.to_thread(list_devices, False)
            payload = {
                "devices": [{"serial": d.serial, "state": d.state} for d in devices],
            }
            return [_json_text(payload)]

        serial = _resolve_serial(arguments.get("serial"))

        if name == "adb_observe":
            include_image = bool(arguments.get("includeImage", False))
            fast = bool(arguments.get("fast", True))
            payload = await asyncio.to_thread(
                observe_screen,
                serial=serial,
                include_image=include_image,
                max_edge=int(arguments.get("maxEdge", 1170)),
                ui_limit=int(arguments.get("uiLimit", 50)),
                fast=fast,
            )
            return _observe_contents(payload, include_image=include_image)

        if name == "adb_observe_wait":
            include_image = bool(arguments.get("includeImage", False))
            fast = bool(arguments.get("fast", True))
            payload = await asyncio.to_thread(
                wait_for_screen_change,
                serial=serial,
                timeout_s=float(arguments.get("timeoutSec", 12)),
                include_image=include_image,
                max_edge=int(arguments.get("maxEdge", 1170)),
                ui_limit=int(arguments.get("uiLimit", 50)),
                fast=fast,
            )
            return _observe_contents(payload, include_image=include_image)

        if name == "adb_activity":
            payload = await asyncio.to_thread(get_foreground_activity, serial=serial)
            return [_json_text(payload)]

        if name == "adb_tap":
            x = int(arguments["x"])
            y = int(arguments["y"])
            await asyncio.to_thread(tap, x=x, y=y, serial=serial)
            return [_json_text({"action": "tap", "x": x, "y": y, "serial": serial})]

        if name == "adb_swipe":
            await asyncio.to_thread(
                swipe,
                x1=int(arguments["x1"]),
                y1=int(arguments["y1"]),
                x2=int(arguments["x2"]),
                y2=int(arguments["y2"]),
                duration_ms=int(arguments.get("durationMs", 350)),
                serial=serial,
            )
            return [
                _json_text(
                    {
                        "action": "swipe",
                        "x1": int(arguments["x1"]),
                        "y1": int(arguments["y1"]),
                        "x2": int(arguments["x2"]),
                        "y2": int(arguments["y2"]),
                        "serial": serial,
                    }
                )
            ]

        raise McpError(ErrorData(code=INVALID_PARAMS, message=f"未知工具: {name}"))

    except AdbError as exc:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=str(exc))) from exc
    except KeyError as exc:
        raise McpError(ErrorData(code=INVALID_PARAMS, message=f"缺少参数: {exc}")) from exc
    except Exception as exc:
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=str(exc))) from exc


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
