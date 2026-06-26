#!/usr/bin/env python3
"""强插需求：区间日均低于 minBracketDailyAvg 时按该值计算档位达标 PK。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parents[1]
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from mse_param_sheet_to_json import (  # noqa: E402
    JSON_SHEET,
    PARAM_SHEET,
    _fetch_sheets_sync,
    _json_sheet_rows,
    _node_id,
    _parse_param_sheet,
    _write_sheet,
)
from mse_sync_to_workbook import _sheet_cell  # noqa: E402


def _string_rows(rows: list[list[Any]]) -> list[list[str]]:
    cols = max(len(r) for r in rows) if rows else 1
    out: list[list[str]] = []
    for row in rows:
        padded = list(row) + [""] * (cols - len(row))
        out.append([_sheet_cell(c) for c in padded])
    return out

WORKBOOK = "https://alidocs.dingtalk.com/i/nodes/EpGBa2Lm8azo5yvyFwOeoB0BWgN7R35y"
MIN_BRACKET_DAILY_AVG = 2000
TIER_NOTE = "有效日均=max(区间日均,minBracketDailyAvg)；达标PK=有效日均×系数"


def _cell(row: list[Any], idx: int) -> str:
    if idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


def _patch_param_sheet(matrix: list[list[Any]]) -> list[list[Any]]:
    out: list[list[Any]] = []
    inserted = False
    title_patched = False

    for row in matrix:
        new_row = list(row)
        block = _cell(row, 0)

        if not title_patched and block.startswith("家族PK服务配置"):
            note = "；区间日均低于 minBracketDailyAvg 时按 minBracketDailyAvg 计算档位"
            if note not in block:
                new_row[0] = block + note
            title_patched = True

        if block == "基础" and _cell(row, 1) == "minListPk" and not inserted:
            out.append(new_row)
            out.append(
                [
                    "基础",
                    "minBracketDailyAvg",
                    MIN_BRACKET_DAILY_AVG,
                    "区间日均兜底：昨日收礼榜均值低于此值时，按此值参与档位达标PK计算",
                    "",
                ]
            )
            inserted = True
            continue

        if block == "档位" and len(new_row) > 6:
            note = _cell(row, 6)
            rank = _cell(row, 2)
            tier = _cell(row, 3)
            if rank and tier and TIER_NOTE not in note:
                prefix = f"{rank} · {tier}档"
                new_row[6] = f"{prefix}；{TIER_NOTE}"

        out.append(new_row)

    if not inserted:
        raise RuntimeError("未找到 minListPk 行，无法插入 minBracketDailyAvg")
    return out


from alidocs_excel_export import _excel_env, _get_token_and_operator  # noqa: E402


async def main_async() -> str:
    workbook_id = _node_id(WORKBOOK)
    url = f"https://alidocs.dingtalk.com/i/nodes/{workbook_id}"
    sheets = _fetch_sheets_sync(url)
    if PARAM_SHEET not in sheets:
        raise RuntimeError(f"缺少工作表「{PARAM_SHEET}」")

    param_rows = _patch_param_sheet(sheets[PARAM_SHEET])
    config, meta = _parse_param_sheet(param_rows)
    json_rows = _json_sheet_rows(meta=meta, config=config)

    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    await _write_sheet(
        token=token,
        operator=operator,
        workbook_id=workbook_id,
        sheet_name=PARAM_SHEET,
        rows=_string_rows(param_rows),
    )
    await _write_sheet(
        token=token,
        operator=operator,
        workbook_id=workbook_id,
        sheet_name=JSON_SHEET,
        rows=json_rows,
    )
    return url


def main() -> int:
    try:
        url = asyncio.run(main_async())
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
