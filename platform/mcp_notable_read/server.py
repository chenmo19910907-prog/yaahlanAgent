#!/usr/bin/env python3
"""钉钉 AI 表格（Notable）只读 MCP。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import McpError
from mcp.types import INTERNAL_ERROR, INVALID_PARAMS, ErrorData, TextContent, Tool

from notable_client import (
    extract_node_id,
    fetch_notable_records,
    records_to_markdown,
    resolve_notable_target,
)

server = Server("dingtalk-notable-read")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="resolve_notable_url",
            description=(
                "解析 alidocs AI 表格链接：nodeId、sheetId、docKey（优先 schedule_links.json）"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "完整 alidocs URL"},
                    "doc_key": {"type": "string", "description": "可选，覆盖 docKey"},
                    "sheet_id": {"type": "string", "description": "可选，覆盖 sheetId"},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="get_notable_records",
            description=(
                "读取钉钉 AI 表格（.able）行数据；返回 Markdown 表或 JSON。"
                "需 DINGTALK_AEGIS_* 与 Notable 读权限。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "alidocs URL（含 sheetId 更佳）"},
                    "doc_key": {"type": "string"},
                    "sheet_id": {"type": "string"},
                    "node_id": {"type": "string"},
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json"],
                        "default": "markdown",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 500,
                        "default": 50,
                        "description": "markdown 模式最多展示行数；json 模式为返回行数上限",
                    },
                    "prefer_cookie": {
                        "type": "boolean",
                        "default": False,
                        "description": "true 时跳过 OpenAPI，仅用 alidocs Cookie（document/data）",
                    },
                },
                "additionalProperties": False,
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "resolve_notable_url":
            url = str(arguments.get("url") or "").strip()
            if not url:
                raise McpError(ErrorData(code=INVALID_PARAMS, message="缺少 url"))
            node_id = extract_node_id(url)
            doc_key, sheet_id, label, source, dentry_key = resolve_notable_target(
                url=url,
                doc_key=str(arguments.get("doc_key") or "").strip(),
                sheet_id=str(arguments.get("sheet_id") or "").strip(),
                node_id=node_id,
            )
            payload = {
                "nodeId": node_id,
                "docKey": doc_key,
                "dentryKey": dentry_key,
                "sheetId": sheet_id,
                "label": label,
                "url": source or url,
            }
            return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]

        if name == "get_notable_records":
            url = str(arguments.get("url") or "").strip()
            doc_key, sheet_id, label, source, _dentry = resolve_notable_target(
                url=url,
                doc_key=str(arguments.get("doc_key") or "").strip(),
                sheet_id=str(arguments.get("sheet_id") or "").strip(),
                node_id=str(arguments.get("node_id") or "").strip(),
            )
            records = await fetch_notable_records(
                doc_key=doc_key,
                sheet_id=sheet_id,
                node_id=str(arguments.get("node_id") or "").strip()
                or (extract_node_id(url) if url else ""),
                url=url,
                prefer_cookie=bool(arguments.get("prefer_cookie")),
            )
            fmt = str(arguments.get("format") or "markdown").lower()
            limit = int(arguments.get("limit") or 50)
            if fmt == "json":
                trimmed = records[:limit]
                text = json.dumps(
                    {
                        "label": label,
                        "docKey": doc_key,
                        "sheetId": sheet_id,
                        "total": len(records),
                        "records": trimmed,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            else:
                text = records_to_markdown(
                    records, label=label, url=source or url, limit=limit
                )
            return [TextContent(type="text", text=text)]

        raise McpError(ErrorData(code=INVALID_PARAMS, message=f"未知工具: {name}"))
    except McpError:
        raise
    except ValueError as exc:
        raise McpError(ErrorData(code=INVALID_PARAMS, message=str(exc))) from exc
    except Exception as exc:
        msg = str(exc)
        if "Notable.Base.Read.All" in msg or "403" in msg:
            msg = f"{msg}（钉钉应用需开通 Notable 读权限）"
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=msg)) from exc


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
