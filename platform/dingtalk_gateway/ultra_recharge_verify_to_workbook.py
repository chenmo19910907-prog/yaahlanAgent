#!/usr/bin/env python3
"""Ultra Recharge 造数验收 Markdown → 钉钉在线表格（多 Sheet）。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parents[1]
_EXCEL_VENV = (
    REPO_ROOT / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel/venv/bin/python3.13"
)

if (
    __name__ == "__main__"
    and _EXCEL_VENV.is_file()
    and Path(sys.executable).resolve() != _EXCEL_VENV.resolve()
):
    os.execv(str(_EXCEL_VENV), [str(_EXCEL_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from alidocs_excel_export import (  # noqa: E402
    ALIDOCS_NODE,
    _create_workbook,
    _excel_env,
    _get_token_and_operator,
    _get_workspace_id,
)
from export_delivery import load_export_config, parse_markdown_table  # noqa: E402
from family_pk_tab_to_workbook import _ensure_sheet, _write_sheet_replace  # noqa: E402
from mse_sync_to_workbook import _sheet_cell  # noqa: E402
from project_paths import temporary_testcase_dir  # noqa: E402

import httpx  # noqa: E402

DEFAULT_MD = temporary_testcase_dir() / "Ultra_Recharge_造数验收.md"

SECTION_SHEETS: list[tuple[str, str]] = [
    ("三、造数验收主表", "造数验收"),
    ("四、分模块功能用例", "UI用例"),
    ("一、配置摘要", "配置摘要"),
    ("六、执行阶段建议", "执行阶段"),
    ("七、阻塞项与待产品确认", "阻塞项"),
    ("八、建议专用账号池", "账号池"),
]


def _string_rows(rows: list[list[Any]]) -> list[list[str]]:
    return [[_sheet_cell(c) for c in row] for row in rows]


def _extract_section(text: str, heading_prefix: str) -> str:
    pattern = re.compile(rf"^##\s*{re.escape(heading_prefix)}[^\n]*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end]


def _section_table(section_text: str) -> list[list[str]] | None:
    rows = parse_markdown_table(section_text)
    if not rows:
        return None
    return _string_rows(rows)


def _meta_rows(md_path: Path, text: str) -> list[list[str]]:
    title_match = re.search(r"^#\s*(.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else md_path.stem
    meta_lines = []
    for line in text.splitlines()[1:20]:
        stripped = line.strip()
        if stripped.startswith("- **") or stripped.startswith("##"):
            if stripped.startswith("##"):
                break
            meta_lines.append(stripped.lstrip("- "))
    rows: list[list[str]] = [["字段", "内容"], ["文档标题", title], ["源文件", str(md_path.relative_to(REPO_ROOT))]]
    for item in meta_lines:
        if "：" in item:
            key, val = item.split("：", 1)
            rows.append([key.replace("**", "").strip(), val.replace("**", "").strip()])
        elif ":" in item:
            key, val = item.split(":", 1)
            rows.append([key.replace("**", "").strip(), val.replace("**", "").strip()])
    rows.append([])
    rows.append(["说明", "各 Sheet 来自 Markdown 对应章节；「造数验收」为主表，执行时回填「结果」列"])
    return rows


def _formula_rows(text: str) -> list[list[str]]:
    section = _extract_section(text, "二、计算公式（造数后手算/脚本算预期）")
    rows: list[list[str]] = [["类型", "公式/说明"]]
    current = ""
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            current = stripped[4:].strip()
        elif stripped.startswith("```"):
            continue
        elif stripped.startswith("- "):
            rows.append([current, stripped[2:].strip()])
        elif stripped and not stripped.startswith("|"):
            rows.append([current, stripped])
    return rows


def parse_markdown_sections(md_path: Path) -> list[tuple[str, list[list[str]]]]:
    text = md_path.read_text(encoding="utf-8")
    sheets: list[tuple[str, list[list[str]]]] = [("说明", _meta_rows(md_path, text))]
    formula = _formula_rows(text)
    if len(formula) > 1:
        sheets.append(("计算公式", formula))
    for heading, sheet_name in SECTION_SHEETS:
        section = _extract_section(text, heading)
        table = _section_table(section)
        if table:
            sheets.append((sheet_name, table))
    if len(sheets) <= 1:
        raise ValueError(f"未解析到任何表格：{md_path}")
    return sheets


async def export_workbook_async(
    *,
    md_path: Path,
    workbook_name: str,
    parent_node_id: str,
) -> str:
    sheets = parse_markdown_sections(md_path)
    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    workspace_id = _get_workspace_id(parent_node_id, "")
    workbook_id = await _create_workbook(
        token=token,
        operator=operator,
        workspace_id=workspace_id,
        parent_node_id=parent_node_id,
        name=workbook_name,
    )
    async with httpx.AsyncClient(timeout=120) as client:
        for sheet_name, rows in sheets:
            await _ensure_sheet(
                token=token,
                operator=operator,
                workbook_id=workbook_id,
                sheet_name=sheet_name,
                client=client,
            )
            await _write_sheet_replace(
                token=token,
                operator=operator,
                workbook_id=workbook_id,
                sheet_name=sheet_name,
                rows=rows,
            )
    return ALIDOCS_NODE.format(node_id=workbook_id)


def export_ultra_recharge_verify_to_workbook(
    *,
    md_path: Path | None = None,
    workbook_name: str | None = None,
    parent_node_id: str | None = None,
) -> dict[str, Any]:
    path = (md_path or DEFAULT_MD).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    title = workbook_name or "Ultra Recharge 造数验收"
    export_cfg = load_export_config()
    parent = (parent_node_id or export_cfg.node_id).strip()
    sheets = parse_markdown_sections(path)
    url = asyncio.run(
        export_workbook_async(md_path=path, workbook_name=title, parent_node_id=parent)
    )
    return {
        "title": title,
        "source": str(path.relative_to(REPO_ROOT)),
        "sheetCount": len(sheets),
        "sheets": [name for name, _ in sheets],
        "workbookUrl": url,
        "configSheetUrl": "https://alidocs.dingtalk.com/i/nodes/amweZ92PV6v2dzZzCMobAyKeVxEKBD6p",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Ultra Recharge 造数验收 Markdown → 钉钉表")
    parser.add_argument("--md", type=Path, default=DEFAULT_MD, help="Markdown 源文件")
    parser.add_argument("--workbook-name", default="Ultra Recharge 造数验收")
    parser.add_argument("--parent-node-id", help="父目录 nodeId")
    args = parser.parse_args()
    out = export_ultra_recharge_verify_to_workbook(
        md_path=args.md,
        workbook_name=args.workbook_name,
        parent_node_id=args.parent_node_id,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
