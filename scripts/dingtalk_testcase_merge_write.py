#!/usr/bin/env python3
"""写入用例表并对功能模块(B)、测试步骤(C)列做纵向合并。"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MCP_WRITE = ROOT / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel"
if str(MCP_WRITE) not in sys.path:
    sys.path.insert(0, str(MCP_WRITE))

import httpx  # noqa: E402
from server_write import (  # noqa: E402
    API_BASE_URL,
    COMMON_HEADERS,
    DEFAULT_AEGIS_KEY,
    DEFAULT_AEGIS_SECRET,
    DEFAULT_WORKID,
    extract_workbook_id_from_url,
    getSheetidByName,
    getTokenAndOperatorId,
    numberToColumnName,
    writeSheetData,
)


def _aegis_creds() -> tuple[str, str, str]:
    return (
        os.getenv("DINGTALK_AEGIS_KEY") or DEFAULT_AEGIS_KEY,
        os.getenv("DINGTALK_AEGIS_SECRET") or DEFAULT_AEGIS_SECRET,
        os.getenv("DINGTALK_WORKID") or DEFAULT_WORKID,
    )

MERGE_API = API_BASE_URL


def _parse_md_table(path: Path) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| RCUI_"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) >= 4:
            rows.append((parts[0], parts[1], parts[2], parts[3]))
    return rows


def _build_grid(cases: list[tuple[str, str, str, str]]) -> list[list[str]]:
    header = ["编号", "功能模块", "测试步骤", "预期结果"]
    grid: list[list[str]] = [header]
    prev_mod = ""
    prev_step = ""
    for cid, mod, step, exp in cases:
        show_mod = mod if mod != prev_mod else ""
        show_step = step if (mod != prev_mod or step != prev_step) else ""
        if show_mod:
            prev_mod = mod
        if show_step or show_mod:
            prev_step = step
        grid.append([cid, show_mod, show_step, exp])
    return grid


def _vertical_merge_ranges(grid: list[list[str]], col_index: int, *, header_rows: int = 1) -> list[tuple[int, int]]:
    """返回 Excel 1-based 行号 (start, end) 含 end。"""
    data = grid[header_rows:]
    ranges: list[tuple[int, int]] = []
    i = 0
    while i < len(data):
        if data[i][col_index]:
            start_data = i
            j = i + 1
            while j < len(data) and not data[j][col_index]:
                j += 1
            if j - start_data > 1:
                excel_start = header_rows + 1 + start_data
                excel_end = header_rows + j
                ranges.append((excel_start, excel_end))
            i = j
        else:
            i += 1
    return ranges


async def _merge_column(
    *,
    workbook_id: str,
    sheet_id: str,
    operator_id: str,
    token: str,
    col_1based: int,
    row_start: int,
    row_end: int,
) -> None:
    col = numberToColumnName(col_1based)
    addr = f"{col}{row_start}:{col}{row_end}"
    url = f"{MERGE_API}/workbooks/{workbook_id}/sheets/{sheet_id}/ranges/{addr}/merge?operatorId={operator_id}"
    headers = {**COMMON_HEADERS, "x-acs-dingtalk-access-token": token}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, json={"mergeType": "mergeAll"})
        resp.raise_for_status()


async def run(url: str, md_path: Path, sheetname: str | None, *, merge_only: bool = False) -> dict[str, Any]:
    cases = _parse_md_table(md_path)
    if not cases:
        raise SystemExit(f"未解析到用例: {md_path}")
    grid = _build_grid(cases)
    if not merge_only:
        await writeSheetData(url, grid, sheetname=sheetname, startRow=1, startColumn=1)

    workbook_id = extract_workbook_id_from_url(url)
    key, secret, workid = _aegis_creds()
    token, operator_id = await getTokenAndOperatorId(key, secret, workid)
    sheet_id, actual_sheet = await getSheetidByName(sheetname, workbook_id, operator_id, token)

    mod_merges = _vertical_merge_ranges(grid, 1)
    step_merges = _vertical_merge_ranges(grid, 2)
    for rs, re in mod_merges:
        await _merge_column(
            workbook_id=workbook_id,
            sheet_id=sheet_id,
            operator_id=operator_id,
            token=token,
            col_1based=2,
            row_start=rs,
            row_end=re,
        )
    for rs, re in step_merges:
        await _merge_column(
            workbook_id=workbook_id,
            sheet_id=sheet_id,
            operator_id=operator_id,
            token=token,
            col_1based=3,
            row_start=rs,
            row_end=re,
        )
    return {
        "url": url,
        "sheet": actual_sheet,
        "rows": len(grid) - 1,
        "module_merges": len(mod_merges),
        "step_merges": len(step_merges),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--md", type=Path, required=True)
    parser.add_argument("--sheetname", default=None)
    parser.add_argument("--merge-only", action="store_true", help="仅合并单元格（表已写入）")
    args = parser.parse_args()
    info = asyncio.run(
        run(args.url, args.md.expanduser(), args.sheetname, merge_only=args.merge_only)
    )
    print(info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
