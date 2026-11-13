#!/usr/bin/env python3
"""解析 perf_case优化 报告，将试跑结果写入钉钉 Sheet「case优化」F 列。"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_SHEET = ROOT / ".cursor/skills/code-testcase-review/scripts/dingtalk_sheet.py"

NODE_URL = "https://alidocs.dingtalk.com/i/nodes/vy20BglGWOekp0O0TmrNb91lJA7depqY"
SHEET_NAME = "case优化"
# 场景01 对应 Excel 第 5 行（1-based）；行号 = 4 + 场景序号
SCENE_ROW_BASE = 4
IMAGE_SKIP = {"03", "09", "23"}


def _load_sheet_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("dingtalk_sheet_perf", SKILL_SHEET)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {SKILL_SHEET}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_report(path: Path) -> tuple[dict[str, str], str]:
    """返回 scene_num -> F列文案, 以及摘要行。"""
    text = path.read_text(encoding="utf-8")
    status: dict[str, str] = {}
    section = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("PASS ("):
            section = "pass"
            continue
        if line.startswith("FAIL ("):
            section = "fail"
            continue
        if line.startswith("PARTIAL/SKIP ("):
            section = "skip"
            continue
        if not line or line.startswith("=") or line.startswith("时间:") or line.startswith("设备:"):
            continue
        if line.startswith("合计"):
            continue
        m = re.match(r"^(\d{1,2})\|", line)
        if not m or section not in ("pass", "fail", "skip"):
            continue
        num = f"{int(m.group(1)):02d}"
        parts = line.split("|", 2)
        title = parts[1] if len(parts) > 1 else ""
        extra = parts[2] if len(parts) > 2 else ""
        if section == "pass":
            status[num] = f"试跑·pass {title}"
        elif section == "fail":
            status[num] = f"试跑·fail {title}"
        else:
            reason = extra or title
            status[num] = f"试跑·skip {reason}"

    bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    n_pass = sum(1 for v in status.values() if v.startswith("试跑·pass"))
    n_fail = sum(1 for v in status.values() if v.startswith("试跑·fail"))
    summary = f"自动化试跑 {bj} | pass {n_pass} fail {n_fail}"
    return status, summary


def build_f_column(status: dict[str, str], image_only: bool) -> list[list[str]]:
    rows: list[list[str]] = []
    for n in range(1, 31):
        num = f"{n:02d}"
        if num in status:
            rows.append([status[num]])
        elif image_only and num in IMAGE_SKIP:
            rows.append(["跳过·需补图（未跑）"])
        else:
            rows.append(["试跑·未执行"])
    return rows


def _write_f_mcp(url: str, start_row: int, values: list[list[str]]) -> None:
    import importlib.util

    mcp_write = ROOT / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel/server_write.py"
    spec = importlib.util.spec_from_file_location("dingtalk_excel_write_mcp", mcp_write)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {mcp_write}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    asyncio.run(
        mod.writeSheetData(
            url=url,
            sheetname=SHEET_NAME,
            data=values,
            startRow=start_row,
            startColumn=6,
        )
    )


async def write_f(url: str, start_row: int, values: list[list[str]], dry: bool) -> None:
    range_preview = f"F{start_row}:F{start_row + len(values) - 1}"
    print(f"将写入 {range_preview}（{len(values)} 行）", file=sys.stderr)
    if dry:
        for i, row in enumerate(values[:5]):
            print(f"  F{start_row + i}: {row[0]}", file=sys.stderr)
        if len(values) > 5:
            print("  ...", file=sys.stderr)
        return
    try:
        sheet_mod = _load_sheet_module()
        sys.path.insert(0, str(ROOT / "scripts"))
        from dingtalk_kb_source import extract_node_id_from_url  # noqa: WPS433

        token, op = await sheet_mod.get_token()
        workbook_id = extract_node_id_from_url(url)
        sheet_id = await sheet_mod.find_sheet_id(token, op, workbook_id, SHEET_NAME)
        if not sheet_id:
            raise RuntimeError(f"未找到 Sheet: {SHEET_NAME}")
        ok = await sheet_mod.write_range(
            token, op, workbook_id, sheet_id, values, start_row=start_row, start_col="F"
        )
        if not ok:
            raise RuntimeError("钉钉 F 列写入失败")
    except Exception as exc:
        print(f"dingtalk_sheet 回退 MCP：{exc}", file=sys.stderr)
        _write_f_mcp(url, start_row, values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        default=str(ROOT / ".tmp/perf_case优化_full_report.txt"),
        help="perf_automation_full.sh 报告路径",
    )
    parser.add_argument("--url", default=NODE_URL)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--mark-image-skip-only",
        action="store_true",
        help="无报告时仅为需补图场景写跳过说明",
    )
    args = parser.parse_args()
    report = Path(args.report)

    if report.is_file():
        status, summary = parse_report(report)
        start_row = SCENE_ROW_BASE + 1
        values = build_f_column(status, image_only=False)
        # 需补图且未出现在报告中的场景
        for num in IMAGE_SKIP:
            if num not in status:
                values[int(num) - 1] = ["跳过·需补图（未跑）"]
    elif args.mark_image_skip_only:
        status, summary = {}, "设备未就绪·仅标记需补图跳过"
        values = build_f_column({}, image_only=True)
        start_row = SCENE_ROW_BASE + 1
    else:
        print(f"报告不存在: {report}", file=sys.stderr)
        return 1

    asyncio.run(write_f(args.url, start_row, values, args.dry_run))
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
