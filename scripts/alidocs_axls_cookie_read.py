"""通过 alidocs Cookie 读取 .axls 工作簿 sheet 名与 Sheet1 概况（OpenAPI 403 时备用）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx

_SCRIPTS = Path(__file__).resolve().parent
_REPO = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_NOTABLE = _REPO / "platform" / "mcp_notable_read"
if str(_NOTABLE) not in sys.path:
    sys.path.insert(0, str(_NOTABLE))

from dingtalk_kb_source import extract_node_id_from_url, resolve_dingtalk_cookie  # noqa: E402
from notable_client import fetch_dentry_key_from_mainsite, USER_AGENT  # noqa: E402

_ALIDOCS_DOCUMENT_DATA = "https://alidocs.dingtalk.com/api/document/data"
_SHEET1_NAMES = frozenset({"Sheet1", "sheet1"})


def _collect_asl_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if "data" in value:
            return _collect_asl_text(value["data"])
        if "value" in value:
            return _collect_asl_text(value["value"])
        return ""
    if isinstance(value, list):
        return "".join(_collect_asl_text(item) for item in value)
    return str(value)


def _rows_from_axls_sheet(sheet: dict[str, Any], *, max_rows: int = 40) -> list[list[Any]]:
    rows_out: list[list[Any]] = []
    raw_rows = sheet.get("rows")
    if not isinstance(raw_rows, list):
        return rows_out
    for row_entry in raw_rows[:max_rows]:
        if not isinstance(row_entry, list) or len(row_entry) < 3:
            continue
        cells_blob = row_entry[2]
        if not isinstance(cells_blob, list):
            continue
        row_values: list[Any] = []
        for cell in cells_blob:
            if not isinstance(cell, list) or len(cell) < 2:
                continue
            payload = cell[1]
            text = ""
            if isinstance(payload, dict):
                inner = payload.get("value")
                if isinstance(inner, dict):
                    text = _collect_asl_text(inner.get("data") or inner)
                else:
                    text = _collect_asl_text(inner)
            row_values.append(text.strip())
        if any(str(v).strip() for v in row_values):
            rows_out.append(row_values)
    return rows_out


def _parse_checkpoint_workbook(content: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    sheets_meta = content.get("sheetsMeta")
    if not isinstance(sheets_meta, list) or not sheets_meta:
        raise RuntimeError("checkpoint 中无 sheetsMeta")

    sheet_names: list[str] = []
    sheet1_rows: list[list[Any]] = []
    sheet_body = content.get("content")
    if not isinstance(sheet_body, dict):
        sheet_body = {}

    for meta in sheets_meta:
        if not isinstance(meta, dict):
            continue
        title = str(meta.get("title") or "").strip()
        sid = str(meta.get("id") or "").strip()
        if title:
            sheet_names.append(title)
        if title in _SHEET1_NAMES and sid and sid in sheet_body:
            inner = sheet_body[sid]
            if isinstance(inner, dict):
                sheet1_rows = _rows_from_axls_sheet(inner)

    if not sheet_names:
        raise RuntimeError("无法解析 sheet 名称")
    return sheet_names, sheet1_rows


async def fetch_workbook_sheets_via_cookie(
    url_or_node_id: str,
    *,
    cookie: str | None = None,
) -> tuple[list[str], list[list[Any]]]:
    node_id = extract_node_id_from_url(url_or_node_id)
    ck = (cookie or resolve_dingtalk_cookie()).strip()
    if not ck:
        raise RuntimeError("缺少 DINGTALK_COOKIE")

    dentry_key = await fetch_dentry_key_from_mainsite(node_id, ck)
    headers = {
        "cookie": ck,
        "user-agent": USER_AGENT,
        "a-dentry-key": dentry_key,
        "content-type": "application/json",
        "origin": "https://alidocs.dingtalk.com",
        "referer": f"https://alidocs.dingtalk.com/i/nodes/{node_id}",
    }
    async with httpx.AsyncClient(verify=False, timeout=90.0) as client:
        resp = await client.post(_ALIDOCS_DOCUMENT_DATA, headers=headers, json={"fetchBody": True})
        if resp.status_code in (401, 403):
            raise RuntimeError("DINGTALK_COOKIE 无效或已过期")
        resp.raise_for_status()
        payload = resp.json()
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    doc_content = data.get("documentContent") if isinstance(data.get("documentContent"), dict) else {}
    checkpoint = doc_content.get("checkpoint") if isinstance(doc_content.get("checkpoint"), dict) else {}
    raw = checkpoint.get("content")
    if not isinstance(raw, str) or not raw.strip().startswith("{"):
        raise RuntimeError("文档 checkpoint 无内联 content（仅 OSS 时不支持 Cookie 读表）")
    workbook = json.loads(raw)
    if not isinstance(workbook, dict):
        raise RuntimeError("checkpoint content 非 JSON 对象")
    return _parse_checkpoint_workbook(workbook)
