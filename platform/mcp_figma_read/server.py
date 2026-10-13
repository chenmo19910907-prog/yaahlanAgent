#!/usr/bin/env python3
"""Figma 只读 MCP（REST API + Personal Access Token，供 Web Agent / SDK 使用）。"""

from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import McpError
from mcp.types import INTERNAL_ERROR, INVALID_PARAMS, ErrorData, TextContent, Tool

FIGMA_API = "https://api.figma.com/v1"
TOKEN_ENV = "FIGMA_ACCESS_TOKEN"

server = Server("figma-read")

_URL_RE = re.compile(
    r"figma\.com/(?:design|file)/([a-zA-Z0-9]+)[^?]*\?(?:[^#]*&)?node-id=([\d]+-[\d]+|[\d]+%3A[\d]+)",
    re.IGNORECASE,
)


def _token() -> str:
    value = (os.environ.get(TOKEN_ENV) or os.environ.get("FIGMA_API_KEY") or "").strip()
    if not value:
        raise McpError(
            ErrorData(
                code=INVALID_PARAMS,
                message=f"未配置 {TOKEN_ENV}，请在 .cursor/.mcp.secrets.json 的 figma-read.env 中填写",
            )
        )
    return value


def _normalize_node_id(raw: str) -> str:
    node = raw.strip().replace("%3A", ":")
    if "-" in node and ":" not in node:
        a, b = node.split("-", 1)
        return f"{a}:{b}"
    return node


def _parse_figma_url(url: str) -> dict[str, str]:
    match = _URL_RE.search(url.strip())
    if not match:
        raise McpError(
            ErrorData(
                code=INVALID_PARAMS,
                message="无法解析 Figma URL，需包含 /design/{fileKey} 与 node-id= 参数",
            )
        )
    return {"fileKey": match.group(1), "nodeId": _normalize_node_id(match.group(2))}


def _figma_get(path: str, query: dict[str, str] | None = None) -> dict[str, Any]:
    qs = urllib.parse.urlencode(query or {})
    url = f"{FIGMA_API}{path}"
    if qs:
        url = f"{url}?{qs}"
    req = urllib.request.Request(
        url,
        headers={"X-Figma-Token": _token(), "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:500]
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"Figma API HTTP {exc.code}: {body}",
            )
        ) from exc
    except urllib.error.URLError as exc:
        raise McpError(
            ErrorData(code=INTERNAL_ERROR, message=f"Figma API 请求失败: {exc.reason}")
        ) from exc
    if not isinstance(data, dict):
        raise McpError(ErrorData(code=INTERNAL_ERROR, message="Figma API 返回非 JSON 对象"))
    return data


def _summarize_node(node: dict[str, Any], *, depth: int, max_depth: int) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": node.get("id"),
        "name": node.get("name"),
        "type": node.get("type"),
    }
    if node.get("type") == "TEXT":
        item["characters"] = node.get("characters")
    bounds = node.get("absoluteBoundingBox")
    if isinstance(bounds, dict):
        item["bounds"] = {
            k: bounds.get(k) for k in ("x", "y", "width", "height") if k in bounds
        }
    if depth >= max_depth:
        return item
    children = node.get("children") or []
    if children:
        item["children"] = [
            _summarize_node(c, depth=depth + 1, max_depth=max_depth)
            for c in children
            if isinstance(c, dict)
        ]
    return item


def _collect_text(node: dict[str, Any], out: list[str]) -> None:
    if node.get("type") == "TEXT":
        text = str(node.get("characters") or "").strip()
        if text:
            out.append(text)
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _collect_text(child, out)


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="parse_figma_url",
            description="从 figma.com 链接解析 fileKey 与 nodeId",
            inputSchema={
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="get_figma_node",
            description="读取 Figma 节点结构摘要（布局层名、TEXT 文案）；可传 url 或 fileKey+nodeId",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "fileKey": {"type": "string"},
                    "nodeId": {"type": "string"},
                    "depth": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 8,
                        "default": 4,
                        "description": "子树深度，默认 4",
                    },
                },
                "additionalProperties": False,
            },
        ),
        Tool(
            name="get_figma_screenshot_url",
            description="获取节点 PNG 导出 URL（有效期约 30 天）",
            inputSchema={
                "type": "object",
                "properties": {
                    "fileKey": {"type": "string"},
                    "nodeId": {"type": "string"},
                    "url": {"type": "string"},
                },
                "additionalProperties": False,
            },
        ),
    ]


def _resolve_keys(arguments: dict[str, Any]) -> tuple[str, str]:
    url = str(arguments.get("url") or "").strip()
    if url:
        parsed = _parse_figma_url(url)
        return parsed["fileKey"], parsed["nodeId"]
    file_key = str(arguments.get("fileKey") or "").strip()
    node_id_raw = str(arguments.get("nodeId") or "").strip()
    if not file_key or not node_id_raw:
        raise McpError(
            ErrorData(code=INVALID_PARAMS, message="需要 url，或同时提供 fileKey 与 nodeId")
        )
    return file_key, _normalize_node_id(node_id_raw)


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    args = arguments or {}
    if name == "parse_figma_url":
        parsed = _parse_figma_url(str(args.get("url") or ""))
        return [TextContent(type="text", text=json.dumps(parsed, ensure_ascii=False, indent=2))]

    if name == "get_figma_node":
        file_key, node_id = _resolve_keys(args)
        depth = int(args.get("depth") or 4)
        depth = max(1, min(8, depth))
        data = _figma_get(
            f"/files/{urllib.parse.quote(file_key)}/nodes",
            {"ids": node_id, "depth": str(depth)},
        )
        node_wrap = (data.get("nodes") or {}).get(node_id) or {}
        document = node_wrap.get("document")
        if not isinstance(document, dict):
            raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"未找到节点 {node_id}"))
        texts: list[str] = []
        _collect_text(document, texts)
        payload = {
            "fileKey": file_key,
            "nodeId": node_id,
            "name": document.get("name"),
            "type": document.get("type"),
            "textSnippets": texts[:200],
            "tree": _summarize_node(document, depth=0, max_depth=depth),
        }
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]

    if name == "get_figma_screenshot_url":
        file_key, node_id = _resolve_keys(args)
        data = _figma_get(
            f"/images/{urllib.parse.quote(file_key)}",
            {"ids": node_id, "format": "png"},
        )
        image_url = (data.get("images") or {}).get(node_id)
        payload = {"fileKey": file_key, "nodeId": node_id, "imageUrl": image_url}
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]

    raise McpError(ErrorData(code=INVALID_PARAMS, message=f"未知工具: {name}"))


async def _main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_main())
