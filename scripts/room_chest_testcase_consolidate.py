#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""汇总仓库内「房间宝箱」相关用例，输出 Markdown + CSV。"""

from __future__ import annotations

import asyncio
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

TEMPLATE_FILES = [
    ROOT / "templates/2026之前活动相关/周年庆-房间宝箱.md",
    ROOT / "templates/2026之前活动相关/房间宝箱优化.md",
    ROOT / "templates/2026之前活动相关/宝箱后台配置-房间宝箱.md",
    ROOT / "templates/2026活动/房间宝箱-超级宝箱优化.md",
]

KB_FILES = [
    ROOT / "testcase-kb/活动.md",
    ROOT / "testcase-kb/礼物.md",
    ROOT / "testcase-kb/房间.md",
    ROOT / "testcase-kb/注册登录.md",
    ROOT / "testcase-kb/神秘人.md",
    ROOT / "testcase-kb/个人主页.md",
    ROOT / "testcase-kb/消息.md",
    ROOT / "testcase-kb/家族.md",
    ROOT / "temporary_testcase/Yaahlan签到业务测试用例.md",
]

SOURCE_KEY = re.compile(r"房间宝箱|Room Chest|room.?chest", re.I)
META_SOURCE = re.compile(r"摘录自[`\"']*:?\s*`?([^`\"'\n]+)`?")
META_VERSION = re.compile(r"\*\*版本\*\*：`([^`]+)`")


@dataclass
class CaseRow:
    module: str
    step: str
    expected: str
    source: str

    def key(self) -> tuple[str, str, str]:
        return (self.module.strip(), self.step.strip(), self.expected.strip())


def _parse_template_md(path: Path) -> list[CaseRow]:
    text = path.read_text(encoding="utf-8")
    source_label = path.stem
    rows: list[CaseRow] = []
    current_module = ""
    in_table = False
    for line in text.splitlines():
        if line.startswith("## 功能模块："):
            current_module = line.split("：", 1)[-1].strip()
            in_table = False
            continue
        if line.strip().startswith("|") and "功能模块" in line and "用例步骤" in line:
            in_table = True
            continue
        if in_table and line.strip().startswith("|") and not line.strip().startswith("|---"):
            parts = [p.strip() for p in line.strip().strip("|").split("|")]
            if len(parts) < 3:
                continue
            mod = parts[0] or current_module
            step = parts[1]
            exp = parts[2] if len(parts) > 2 else ""
            if mod == "功能模块" or step == "用例步骤描述":
                continue
            if not step and not exp:
                continue
            if not exp:
                exp = step
            rows.append(CaseRow(mod, step, exp, source_label))
    return rows


def _parse_kb_md(path: Path) -> list[CaseRow]:
    text = path.read_text(encoding="utf-8")
    rows: list[CaseRow] = []
    current_module = ""
    current_source = path.name
    current_version = "—"
    include_block = False

    for line in text.splitlines():
        if line.startswith("### "):
            current_module = line[4:].strip()
            include_block = "房间宝箱" in current_module
            continue
        m = META_SOURCE.search(line)
        if m:
            src = m.group(1).strip()
            current_source = src
            include_block = bool(SOURCE_KEY.search(src)) or bool(
                SOURCE_KEY.search(current_module)
            )
        vm = META_VERSION.search(line)
        if vm:
            current_version = vm.group(1).strip()
        if line.startswith("## ") and "房间宝箱" in line:
            include_block = True
            current_module = line[3:].strip()
            continue
        if not include_block and not SOURCE_KEY.search(line):
            continue
        if line.startswith("- "):
            body = line[2:].strip()
            if not body or body.startswith("（无额外规则说明）"):
                continue
            src = f"{current_version} · {current_source}"
            rows.append(
                CaseRow(
                    module=current_module or "房间宝箱",
                    step=body,
                    expected=body,
                    source=src,
                )
            )
    return rows


async def _fetch_v227_sheet_rows() -> list[CaseRow]:
    try:
        from dingtalk_kb_source import discover_workbooks, resolve_folder_url, resolve_dingtalk_cookie
        from alidocs_axls_cookie_read import fetch_workbook_sheets_via_cookie
    except ImportError:
        return []

    folder_url, _ = resolve_folder_url(folder_id="yaahlan-testcases")
    try:
        resolve_dingtalk_cookie()
    except RuntimeError:
        return []

    workbooks = discover_workbooks(folder_url, recursive=True)
    target = None
    for wb in workbooks:
        if wb.version_tuple == (2, 2, 7) or "2.2.7版本用例" in wb.name:
            target = wb
            break
    if not target:
        return []

    try:
        names, sheet1 = await fetch_workbook_sheets_via_cookie(target.url)
    except Exception:
        return []

    rows: list[CaseRow] = []
    # OpenAPI fallback path not implemented here; cookie path returns names only without cell matrix
    # Parse sheet1 overview if present; primary: use sheet name list as index row
    _ = sheet1

    # Re-fetch full sheets via openapi if available
    report_root = ROOT / "Report"
    if str(report_root) not in sys.path:
        sys.path.insert(0, str(report_root))
    try:
        from report.dingtalk_xlsx import fetch_workbook_sheets

        sheets = await fetch_workbook_sheets(target.url)
    except Exception:
        sheets = []

    sheet_map = {n: data for n, data in sheets} if sheets else {}
    for name in names:
        if name.strip() not in ("房间宝箱", "Sheet1") and "房间宝箱" not in name:
            if name not in sheet_map:
                continue
        data = sheet_map.get(name) or sheet_map.get("房间宝箱") or []
        if not data:
            continue
        module = name
        for row in data[1:]:
            if not isinstance(row, list):
                continue
            cells = [str(c or "").strip() for c in row]
            while cells and not cells[-1]:
                cells.pop()
            if not any(cells):
                continue
            if len(cells) >= 4:
                mod, step, exp = cells[1], cells[2], cells[3]
            elif len(cells) == 3:
                mod, step, exp = cells[0], cells[1], cells[2]
            elif len(cells) == 2:
                mod, step, exp = module, cells[0], cells[1]
            else:
                mod, step, exp = module, cells[0], cells[0]
            if mod in ("功能模块", "用例步骤描述", "测试步骤"):
                continue
            if not step and not exp:
                continue
            rows.append(
                CaseRow(
                    module=mod or module,
                    step=step or exp,
                    expected=exp or step,
                    source=f"v2.2.7 · {target.name} · {name}",
                )
            )
    return rows


def consolidate() -> list[CaseRow]:
    merged: list[CaseRow] = []
    seen: set[tuple[str, str, str]] = set()

    def add_all(items: list[CaseRow]) -> None:
        for item in items:
            k = item.key()
            if not k[1]:
                continue
            if k in seen:
                continue
            seen.add(k)
            merged.append(item)

    for path in TEMPLATE_FILES:
        if path.is_file():
            add_all(_parse_template_md(path))
    for path in KB_FILES:
        if path.is_file():
            add_all(_parse_kb_md(path))

    try:
        add_all(asyncio.run(_fetch_v227_sheet_rows()))
    except Exception:
        pass
    return merged


def write_outputs(rows: list[CaseRow], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "房间宝箱-功能汇总用例.md"
    csv_path = out_dir / "房间宝箱-功能汇总用例.csv"

    lines = [
        "# 房间宝箱 · 功能汇总测试用例",
        "",
        "| 编号 | 功能模块 | 测试步骤 | 预期结果 | 来源 |",
        "|------|----------|----------|----------|------|",
    ]
    csv_rows = [["编号", "功能模块", "测试步骤", "预期结果", "来源"]]
    for i, row in enumerate(rows, start=1):
        cid = f"RC_{i:04d}"
        lines.append(
            f"| {cid} | {row.module} | {row.step} | {row.expected} | {row.source} |"
        )
        csv_rows.append([cid, row.module, row.step, row.expected, row.source])

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(csv_rows)
    return md_path, csv_path


def main() -> int:
    rows = consolidate()
    md_path, csv_path = write_outputs(rows, ROOT / "temporary_testcase")
    print(f"用例条数: {len(rows)}")
    print(f"Markdown: {md_path}")
    print(f"CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
