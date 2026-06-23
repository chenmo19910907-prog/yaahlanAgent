#!/usr/bin/env python3
"""从 schedule_links.json 登记链接实时拉取排期表（不写入知识库正文）。"""

from __future__ import annotations

import argparse
import asyncio
import json
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


async def _fetch_notable_records(
    *,
    doc_key: str,
    sheet_id: str,
) -> list[dict[str, Any]]:
    import httpx

    from dingtalk_kb_source import resolve_aegis_credentials, _import_server_read

    mod = _import_server_read()
    ak, sec, wid = resolve_aegis_credentials()
    access, op = await mod.getTokenAndOperatorId(ak, sec, wid)
    url = f"https://api.dingtalk.com/v1.0/notable/bases/{doc_key}/sheets/{sheet_id}/records/list"
    headers = {"x-acs-dingtalk-access-token": access, "content-type": "application/json"}
    records: list[dict[str, Any]] = []
    next_token = ""
    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            body: dict[str, Any] = {"maxResults": 100}
            if next_token:
                body["nextToken"] = next_token
            resp = await client.post(url, params={"operatorId": op}, headers=headers, json=body)
            resp.raise_for_status()
            payload = resp.json()
            batch = payload.get("records") or []
            if isinstance(batch, list):
                records.extend(r for r in batch if isinstance(r, dict))
            next_token = str(payload.get("nextToken") or "").strip()
            if not next_token or not batch:
                break
    return records


def _field_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts = [_field_text(v) for v in value]
        return "、".join(p for p in parts if p)
    if isinstance(value, dict):
        for key in ("name", "text", "title", "label", "value"):
            if value.get(key) not in (None, ""):
                return _field_text(value.get(key))
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _records_to_markdown(
    records: list[dict[str, Any]],
    *,
    label: str,
    url: str,
    limit: int = 30,
) -> str:
    if not records:
        return f"**{label}** 当前无记录。\n\n来源：{url}"

    field_names: list[str] = []
    seen: set[str] = set()
    for rec in records:
        fields = rec.get("fields")
        if not isinstance(fields, dict):
            continue
        for name in fields:
            if name not in seen:
                seen.add(name)
                field_names.append(str(name))

    if not field_names:
        return f"**{label}** 已拉取 {len(records)} 条，但字段为空。\n\n来源：{url}"

    lines = [
        f"**{label}**（实时自钉钉拉取，共 {len(records)} 条）",
        "",
        "| " + " | ".join(field_names) + " |",
        "| " + " | ".join(["---"] * len(field_names)) + " |",
    ]
    shown = records[:limit]
    for rec in shown:
        fields = rec.get("fields") if isinstance(rec.get("fields"), dict) else {}
        row = [_field_text(fields.get(name)) for name in field_names]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |")
    if len(records) > limit:
        lines.extend(
            [
                "",
                f"…（共 {len(records)} 条，已展示前 {limit} 条；回复「查看全部数据」可看完整列表）",
            ]
        )
    lines.extend(["", f"来源：{url}"])
    return "\n".join(lines)


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
            records = asyncio.run(_fetch_notable_records(doc_key=doc_key, sheet_id=sheet_id))
            return _records_to_markdown(records, label=label, url=url)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "Notable.Base.Read.All" in msg or "403" in msg:
                return (
                    f"排期表 **{label}** 为钉钉 AI 表格（.able），当前应用未开通 Notable 读权限，"
                    f"无法自动拉取最新行数据。\n\n"
                    f"请直接打开链接查看：{url}\n\n"
                    f"或在钉钉中导出为 Excel/.axls 后 @ 机器人导入查询。"
                )
            return f"拉取 **{label}** 失败：{msg}\n\n请打开链接查看：{url}"

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
