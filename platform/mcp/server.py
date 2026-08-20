#!/usr/bin/env python3
"""平台能力统一 MCP Server — registry 驱动，覆盖 Admin/MOA/Tunnel 等全部模块。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import McpError
from mcp.types import INTERNAL_ERROR, INVALID_PARAMS, ErrorData, TextContent, Tool

_MCP_DIR = Path(__file__).resolve().parent
if str(_MCP_DIR) not in sys.path:
    sys.path.insert(0, str(_MCP_DIR))

from catalog import (  # noqa: E402
    build_capability_argv,
    get_capability,
    list_module_capabilities,
    load_catalog,
    search_capabilities,
)
from runner import run_argv, run_module_cli  # noqa: E402

server = Server("platform-tools")


def _json_text(payload: Any) -> TextContent:
    return TextContent(
        type="text",
        text=json.dumps(payload, ensure_ascii=False, indent=2),
    )


def _require_str(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if value is None or str(value).strip() == "":
        raise McpError(
            ErrorData(code=INVALID_PARAMS, message=f"缺少参数: {key}")
        )
    return str(value).strip()


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_modules",
            description="列出平台全部模块（Admin/MOA/Tunnel/Gift/Risk/MSE/workflow/online/adb 等）及能力数量",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        Tool(
            name="search_capabilities",
            description="按关键字搜索 registry 能力（名称/分类/描述/prompts）",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键字；空则返回前 N 条",
                    },
                    "module_id": {
                        "type": "string",
                        "description": "限定模块，如 admin/moa/tunnel",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 20,
                    },
                },
                "additionalProperties": False,
            },
        ),
        Tool(
            name="list_capabilities",
            description="列出某模块的全部 registry 能力",
            inputSchema={
                "type": "object",
                "properties": {
                    "module_id": {"type": "string"},
                    "category": {
                        "type": "string",
                        "description": "按分类过滤（子串匹配）",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 500,
                        "default": 200,
                    },
                },
                "required": ["module_id"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="get_capability",
            description="获取单个能力的 command 模板与 parameters",
            inputSchema={
                "type": "object",
                "properties": {
                    "module_id": {"type": "string"},
                    "capability_id": {"type": "string"},
                },
                "required": ["module_id", "capability_id"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="run_capability",
            description="按 module_id + capability_id 执行 registry 能力；parameters 填占位符",
            inputSchema={
                "type": "object",
                "properties": {
                    "module_id": {"type": "string"},
                    "capability_id": {"type": "string"},
                    "parameters": {
                        "type": "object",
                        "description": "占位符键值，如 userId/roomId/phone",
                        "additionalProperties": {"type": "string"},
                    },
                    "timeout_sec": {"type": "integer", "default": 120},
                },
                "required": ["module_id", "capability_id"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="run_module_cli",
            description="直接调用模块 entry（如 adb --help）；args 为 CLI 参数数组",
            inputSchema={
                "type": "object",
                "properties": {
                    "module_id": {"type": "string"},
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": '不含 python 与脚本路径，如 ["--query-user-id", "123"]',
                    },
                    "timeout_sec": {"type": "integer", "default": 120},
                },
                "required": ["module_id"],
                "additionalProperties": False,
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "list_modules":
            modules, capabilities = load_catalog()
            return [
                _json_text(
                    {
                        "modules": [m.to_dict() for m in modules],
                        "total_capabilities": len(capabilities),
                    }
                )
            ]

        if name == "search_capabilities":
            query = str(arguments.get("query") or "")
            module_id = str(arguments.get("module_id") or "").strip() or None
            limit = int(arguments.get("limit") or 20)
            items = search_capabilities(query, module_id=module_id, limit=limit)
            return [
                _json_text(
                    {
                        "query": query,
                        "module_id": module_id or "",
                        "count": len(items),
                        "items": [c.to_summary() for c in items],
                    }
                )
            ]

        if name == "list_capabilities":
            module_id = _require_str(arguments, "module_id")
            category = str(arguments.get("category") or "").strip() or None
            limit = int(arguments.get("limit") or 200)
            items = list_module_capabilities(
                module_id, category=category, limit=limit
            )
            return [
                _json_text(
                    {
                        "module_id": module_id,
                        "category": category or "",
                        "count": len(items),
                        "items": [c.to_summary() for c in items],
                    }
                )
            ]

        if name == "get_capability":
            module_id = _require_str(arguments, "module_id")
            capability_id = _require_str(arguments, "capability_id")
            cap = get_capability(module_id, capability_id)
            if cap is None:
                raise McpError(
                    ErrorData(
                        code=INVALID_PARAMS,
                        message=f"未找到能力: {module_id}/{capability_id}",
                    )
                )
            return [_json_text(cap.to_detail())]

        if name == "run_capability":
            module_id = _require_str(arguments, "module_id")
            capability_id = _require_str(arguments, "capability_id")
            params = arguments.get("parameters") or {}
            if not isinstance(params, dict):
                raise McpError(
                    ErrorData(code=INVALID_PARAMS, message="parameters 必须是 object")
                )
            timeout_sec = int(arguments.get("timeout_sec") or 120)
            argv = build_capability_argv(module_id, capability_id, params)
            result = run_argv(argv, timeout_sec=timeout_sec)
            return [_json_text(result)]

        if name == "run_module_cli":
            module_id = _require_str(arguments, "module_id")
            args_raw = arguments.get("args") or []
            if not isinstance(args_raw, list) or not all(
                isinstance(a, str) for a in args_raw
            ):
                raise McpError(
                    ErrorData(code=INVALID_PARAMS, message="args 必须是 string 数组")
                )
            timeout_sec = int(arguments.get("timeout_sec") or 120)
            result = run_module_cli(module_id, args_raw, timeout_sec=timeout_sec)
            return [_json_text(result)]

        raise McpError(
            ErrorData(code=INVALID_PARAMS, message=f"未知工具: {name}")
        )
    except McpError:
        raise
    except ValueError as exc:
        raise McpError(ErrorData(code=INVALID_PARAMS, message=str(exc))) from exc
    except Exception as exc:
        raise McpError(
            ErrorData(code=INTERNAL_ERROR, message=str(exc))
        ) from exc


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
