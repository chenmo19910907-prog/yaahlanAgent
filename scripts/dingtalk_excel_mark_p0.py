#!/usr/bin/env python3
"""钉钉在线用例表：按优先级在「预期结果」列标 P0 绿色填充（不改单元格文案）。"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from mcp_paths import load_mcp_env  # noqa: E402

_MCP_EXCEL = ROOT / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel"
sys.path.insert(0, str(_MCP_EXCEL))
from server_read import (  # noqa: E402
    API_BASE_URL,
    COMMON_HEADERS,
    extract_workbook_id_from_url,
    getSheetInfo,
    getSheetList,
    getTokenAndOperatorId,
)

P0_COLOR = "#92D050"
WHITE = "#FFFFFF"
HDR_D = "#B7DEE8"
DEFAULT_RATIO = 0.20

SKIP_MODULES = (
    "翻译",
    "镜像",
    "关联场景",
    "新老版本",
    "老版本历史",
    "定时任务",
    "失败与回滚",
    "各场景case",
    "幂等",
    "弱网",
    "性能",
    "兼容性",
    "用例编写规范",
)
SKIP_IN = ("倒计时", "实时更新", "归零", "仅限匹配", "玩法详情", "距离活动", "距离结束")
SKIP_START = ("设置", "开启")


def find_header_idx(vals: list[list]) -> int | None:
    for i, row in enumerate(vals):
        if len(row) > 3 and str(row[3] or "").strip() == "预期结果":
            return i
    return None


def eligible(cur_mod: str, expected: str) -> bool:
    exp = str(expected or "").strip()
    if not exp or exp == "预期结果":
        return False
    if any(s in cur_mod for s in SKIP_MODULES):
        return False
    if any(s in exp for s in SKIP_IN):
        return False
    if any(exp.startswith(s) for s in SKIP_START):
        return False
    return True


def score_row(cur_mod: str, step: str, expected: str) -> int:
    s = 0
    e = expected.strip()
    st = step.strip()
    if e.startswith("展示") and (
        "20点" in e or "面板" in e or "弹窗" in e or "tab" in e.lower() or "状态" in e
    ):
        s += 100
    elif e.startswith("展示"):
        s += 70
    if e.startswith("可以") and ("切换" in e or "跨房" in e):
        s += 95
    elif e.startswith("可以"):
        s += 50
    if "正常" in e and not e.startswith(("设置", "开启")):
        s += 40
    if "跳转" in e or "点击" in e:
        s += 15
    if "不展示" in e or "无法" in e or "关闭后" in e:
        s += 25
    if st and len(st) < 30:
        s += 5
    if "跨房" in cur_mod or "PK" in cur_mod or "吃鸡" in cur_mod:
        s += 10
    return s


def build_row_colors(vals: list[list], ratio: float) -> tuple[dict[int, str], int, int]:
    hdr_i = find_header_idx(vals)
    if hdr_i is None:
        return {}, 0, 0
    cur_mod = ""
    candidates: list[tuple[int, int]] = []
    all_rows: dict[int, str] = {}
    for i in range(hdr_i + 1, len(vals)):
        row = vals[i]
        excel_row = i + 1
        b = str(row[1] if len(row) > 1 else "").strip()
        c = str(row[2] if len(row) > 2 else "").strip()
        d = str(row[3] if len(row) > 3 else "").strip()
        if b:
            cur_mod = b
        if not d:
            continue
        all_rows[excel_row] = WHITE
        if eligible(cur_mod, d):
            candidates.append((score_row(cur_mod, c, d), excel_row))
    n = len(candidates)
    k = max(1, math.ceil(n * ratio)) if n else 0
    candidates.sort(key=lambda x: (-x[0], x[1]))
    for _, row in candidates[:k]:
        all_rows[row] = P0_COLOR
    all_rows[hdr_i + 1] = HDR_D
    return all_rows, k, n


def to_contiguous_ranges(row_color_map: dict[int, str]) -> list[tuple[int, int, str]]:
    rows = sorted(row_color_map)
    out: list[tuple[int, int, str]] = []
    i = 0
    while i < len(rows):
        r = rows[i]
        color = row_color_map[r]
        j = i + 1
        while (
            j < len(rows)
            and rows[j] == rows[j - 1] + 1
            and row_color_map[rows[j]] == color
        ):
            j += 1
        out.append((r, rows[j - 1], color))
        i = j
    return out


async def fetch_sheet_values(wb: str, sid: str, op: str, tok: str, nrows: int) -> list[list]:
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.get(
            f"{API_BASE_URL}/workbooks/{wb}/sheets/{sid}/ranges/A1:O{nrows}?select=values&operatorId={op}",
            headers={**COMMON_HEADERS, "x-acs-dingtalk-access-token": tok},
        )
        r.raise_for_status()
        return r.json()["values"]


async def apply_colors(
    wb: str,
    sid: str,
    op: str,
    tok: str,
    row_color_map: dict[int, str],
    *,
    dry_run: bool,
) -> int:
    if dry_run:
        return sum(1 for c in row_color_map.values() if c == P0_COLOR)
    headers = {**COMMON_HEADERS, "x-acs-dingtalk-access-token": tok}
    applied = 0
    async with httpx.AsyncClient(timeout=180) as client:
        for r1, r2, color in to_contiguous_ranges(row_color_map):
            n = r2 - r1 + 1
            payload = {"backgroundColors": [[color] for _ in range(n)]}
            range_str = f"D{r1}:D{r2}"
            url = f"{API_BASE_URL}/workbooks/{wb}/sheets/{sid}/ranges/{range_str}?operatorId={op}"
            resp = await client.put(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"{range_str} HTTP {resp.status_code}: {resp.text[:400]}")
            if color == P0_COLOR:
                applied += n
    return applied


def sheet_matches(name: str, sheet_filter: str | None, sheet_names: list[str] | None) -> bool:
    if sheet_names:
        return name in sheet_names
    if sheet_filter:
        return sheet_filter in name
    return True


async def run(args: argparse.Namespace) -> dict:
    env = load_mcp_env("dingtalk-excel-write")
    key, sec, wid = env["DINGTALK_AEGIS_KEY"], env["DINGTALK_AEGIS_SECRET"], env["DINGTALK_WORKID"]
    wb = extract_workbook_id_from_url(args.url)
    tok, op = await getTokenAndOperatorId(key, sec, wid)
    sheets = await getSheetList(wb, op, tok)
    sheet_names = [s.strip() for s in args.sheets.split(",") if s.strip()] if args.sheets else None

    summary: list[dict] = []
    total_p0 = total_eligible = 0
    for sh in sheets:
        if not sheet_matches(sh["name"], args.sheet_contains, sheet_names):
            continue
        data, _ = await getSheetInfo(
            args.url,
            sheetname=sh["name"],
            aegisKey=key,
            aegisSecret=sec,
            workid=wid,
        )
        nrows = max(len(data) + 10, 80)
        vals = await fetch_sheet_values(wb, sh["id"], op, tok, nrows)
        row_colors, p0_n, el_n = build_row_colors(vals, args.ratio)
        if not row_colors:
            summary.append({"sheet": sh["name"], "status": "no_header", "p0": 0, "eligible": 0})
            continue
        if not args.dry_run:
            await apply_colors(wb, sh["id"], op, tok, row_colors, dry_run=False)
        pct = (p0_n / el_n * 100) if el_n else 0.0
        summary.append(
            {
                "sheet": sh["name"],
                "status": "ok",
                "p0": p0_n,
                "eligible": el_n,
                "ratio_pct": round(pct, 1),
            }
        )
        total_p0 += p0_n
        total_eligible += el_n
        await asyncio.sleep(0.12)

    return {
        "url": args.url,
        "ratio": args.ratio,
        "dry_run": args.dry_run,
        "sheets": summary,
        "total_p0": total_p0,
        "total_eligible": total_eligible,
        "total_ratio_pct": round(total_p0 / total_eligible * 100, 1) if total_eligible else 0,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="钉钉用例表 D 列标 P0 绿色（#92D050）")
    p.add_argument("url", help="钉钉 alidocs 工作簿 URL")
    p.add_argument(
        "--ratio",
        type=float,
        default=DEFAULT_RATIO,
        help=f"P0 占可入选预期行比例（默认 {DEFAULT_RATIO}）",
    )
    p.add_argument(
        "--sheet-contains",
        metavar="TEXT",
        help="仅处理 Sheet 名称包含该子串的页（如 跨房PK）",
    )
    p.add_argument(
        "--sheets",
        metavar="N1,N2",
        help="仅处理指定 Sheet 名（逗号分隔，优先于 --sheet-contains）",
    )
    p.add_argument("--dry-run", action="store_true", help="只统计不写入背景色")
    p.add_argument("--json", action="store_true", help="输出 JSON 摘要")
    args = p.parse_args()
    if not 0 < args.ratio <= 1:
        print("ratio 须在 (0, 1]", file=sys.stderr)
        return 2
    result = asyncio.run(run(args))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for row in result["sheets"]:
            if row["status"] != "ok":
                print(f"{row['sheet']}: {row['status']}")
            else:
                print(
                    f"{row['sheet']}: P0={row['p0']} eligible={row['eligible']} ({row['ratio_pct']}%)"
                )
        print(
            f"TOTAL: P0={result['total_p0']} eligible={result['total_eligible']} "
            f"({result['total_ratio_pct']}%)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
