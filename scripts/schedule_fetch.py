#!/usr/bin/env python3
"""从 schedule_links.json 登记链接实时拉取排期表（不写入知识库正文）。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "documents" / "schedule_links.json"
_MCP_PYTHON = ROOT / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel/venv/bin/python3.13"

if _MCP_PYTHON.is_file() and Path(sys.executable).resolve() != _MCP_PYTHON.resolve():
    import os

    os.execv(str(_MCP_PYTHON), [str(_MCP_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])

if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))


def load_registry() -> dict[str, Any]:
    if not REGISTRY.is_file():
        raise FileNotFoundError(f"排期链接登记缺失：{REGISTRY}")
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if not isinstance(data.get("schedules"), list):
        raise ValueError("schedule_links.json 缺少 schedules 数组")
    return data


def list_schedules() -> list[dict[str, Any]]:
    return list(load_registry().get("schedules") or [])


def resolve_schedule(query: str) -> dict[str, Any] | None:
    text = (query or "").strip()
    if not text:
        return None
    schedules = list_schedules()
    if text in {str(s.get("id") or "") for s in schedules}:
        for item in schedules:
            if str(item.get("id") or "") == text:
                return item
    lower = text.lower()
    for item in schedules:
        label = str(item.get("label") or "")
        if label and label.lower() in lower:
            return item
        for alias in item.get("aliases") or []:
            if str(alias).lower() in lower:
                return item
    if re.search(r"排期", text):
        if len(schedules) == 1:
            return schedules[0]
    return None


def _sheet_id_from_entry(entry: dict[str, Any]) -> str:
    sheet_id = str(entry.get("sheetId") or "").strip()
    if sheet_id:
        return sheet_id
    url = str(entry.get("url") or "")
    qs = parse_qs(urlparse(url).query)
    iframe = qs.get("iframeQuery", [""])[0]
    inner = parse_qs(iframe) if iframe else {}
    return str((inner.get("sheetId") or [""])[0] or "").strip()


def _notable_client():
    notable_dir = ROOT / "platform" / "mcp_notable_read"
    if str(notable_dir) not in sys.path:
        sys.path.insert(0, str(notable_dir))
    import notable_client as mod

    return mod


def fetch_schedule_live(entry: dict[str, Any]) -> str:
    label = str(entry.get("label") or entry.get("id") or "排期表")
    url = str(entry.get("url") or "").strip()
    fmt = str(entry.get("format") or "").lower()

    if fmt == "able" or fmt == "notable":
        doc_key = str(entry.get("docKey") or "").strip()
        sheet_id = _sheet_id_from_entry(entry)
        if not doc_key or not sheet_id:
            return (
                f"排期表 **{label}** 登记缺少 docKey/sheetId，暂无法自动拉取。\n"
                f"请打开链接查看：{url}"
            )
        try:
            nc = _notable_client()
            from dingtalk_kb_source import resolve_aegis_credentials

            ak, sec, wid = resolve_aegis_credentials()
            os.environ.setdefault("DINGTALK_AEGIS_KEY", ak)
            os.environ.setdefault("DINGTALK_AEGIS_SECRET", sec)
            os.environ.setdefault("DINGTALK_WORKID", wid)
            node_id = nc.extract_node_id(url) if url else ""
            records = asyncio.run(
                nc.fetch_notable_records(
                    doc_key=doc_key,
                    sheet_id=sheet_id,
                    node_id=node_id,
                    url=url,
                )
            )
            return nc.records_to_markdown(records, label=label, url=url, limit=30)
        except Exception as exc:  # noqa: BLE001
            return f"拉取 **{label}** 失败：{exc}\n\n链接：{url}"

    if fmt in {"axls", "xlsx", "xls"}:
        from dingtalk_kb_source import fetch_workbook_sheets

        try:
            sheets = fetch_workbook_sheets(url)
        except Exception as exc:  # noqa: BLE001
            return f"拉取 **{label}** 失败：{exc}\n\n链接：{url}"
        lines = [f"**{label}**（实时自钉钉拉取）", ""]
        for sheet_name, matrix in sheets[:3]:
            if not matrix:
                continue
            headers = [str(c or "") for c in matrix[0]]
            lines.append(f"### {sheet_name}")
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for row in matrix[1:31]:
                cells = [str(c or "") for c in row[: len(headers)]]
                while len(cells) < len(headers):
                    cells.append("")
                lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
            if len(matrix) > 31:
                lines.append(f"\n…（{sheet_name} 共 {len(matrix) - 1} 行，已展示前 30 行）")
            lines.append("")
        lines.append(f"来源：{url}")
        return "\n".join(lines).strip()

    return f"排期表 **{label}** 格式 `{fmt or '未知'}` 暂不支持自动拉取。\n\n链接：{url}"


def format_schedule_list() -> str:
    items = list_schedules()
    if not items:
        return "当前未登记任何排期表链接。"
    lines = ["已登记排期表（仅链接，查询时实时拉取）：", ""]
    for item in items:
        lines.append(f"- **{item.get('label')}**：{item.get('url')}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="排期表链接登记 + 实时拉取")
    parser.add_argument("query", nargs="?", default="", help="排期关键词或 id")
    parser.add_argument("--list", action="store_true", help="列出已登记链接")
    parser.add_argument("--id", default="", help="按 id 拉取")
    args = parser.parse_args()

    if args.list:
        print(format_schedule_list())
        return 0

    query = (args.id or args.query or "").strip()
    if not query:
        print(format_schedule_list())
        return 0

    entry = resolve_schedule(query)
    if entry is None:
        print(f"未匹配到排期表登记，关键词：{query!r}\n\n{format_schedule_list()}", file=sys.stderr)
        return 1

    print(fetch_schedule_live(entry))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
