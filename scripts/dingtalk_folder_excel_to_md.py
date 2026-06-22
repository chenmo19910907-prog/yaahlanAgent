#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""钉钉目录下 Excel 测试用例 → 本地 Markdown（按 rules/dingtalk_historical_testcase_to_md.md）。"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Tuple

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from dingtalk_kb_source import (  # noqa: E402
    extract_node_id_from_url,
    fetch_workbook_sheets,
    is_spreadsheet_entry,
    list_folder_children_via_box,
    resolve_dingtalk_cookie,
)
from xlsx_kb_sync import CaseRow, iter_cases_from_matrix  # noqa: E402

NOISE_RE = re.compile(r"覆盖率任务|老版本|翻译|镜像\s*case", re.I)
PLACEHOLDER_RE = re.compile(
    r"^(无|具体case|方案|不需要/具体case|不需要|N/?A)$",
    re.I,
)
SHELL_MODULE_HINTS = (
    "版本限制",
    "分区",
    "风控",
    "安全",
    "灰度",
    "回测",
    "测试工具需求",
    "边界-",
    "异常-",
    "兼容-",
    "发散-",
    "回归-",
    "审计-",
    "越权",
    "各场景case完善检查",
)
INVALID_FS_CHARS = re.compile(r'[\\/:*?"<>|]')


def _safe_filename(name: str) -> str:
    return INVALID_FS_CHARS.sub("_", (name or "").strip()) or "untitled"


def _workbook_stem(name: str) -> str:
    base = (name or "").strip()
    if "." in base:
        base = base.rsplit(".", 1)[0]
    return _safe_filename(base)


def _should_filter_noise(module: str, step: str) -> bool:
    return bool(NOISE_RE.search(f"{module} {step}"))


def _is_shell_module(module: str, rows: List[CaseRow]) -> bool:
    mod = (module or "").strip()
    if not mod:
        return False
    if any(h in mod for h in SHELL_MODULE_HINTS):
        if len(rows) == 1:
            step = rows[0].step.strip()
            expects = [e.strip() for e in rows[0].expects if e.strip()]
            if not step and len(expects) <= 1:
                only = expects[0] if expects else ""
                if not only or PLACEHOLDER_RE.match(only):
                    return True
            if PLACEHOLDER_RE.match(step) and (not expects or all(PLACEHOLDER_RE.match(e) for e in expects)):
                return True
    return False


def _escape_cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", "<br>").strip()


def _format_step(step: str) -> str:
    lines = [ln.strip() for ln in (step or "").splitlines() if ln.strip()]
    if not lines:
        return ""
    if any(re.match(r"^\d+\.", ln) for ln in lines):
        return "<br>".join(lines)
    if len(lines) == 1:
        return lines[0]
    return "<br>".join(f"{i}. {ln}" for i, ln in enumerate(lines, 1))


def _expand_rows(cases: List[CaseRow]) -> List[Tuple[str, str, str]]:
    out: List[Tuple[str, str, str]] = []
    for case in cases:
        module = case.module or "未分类"
        step = _format_step(case.step)
        expects = [e.strip() for e in case.expects if e and str(e).strip()]
        if not expects:
            if step:
                out.append((module, step, ""))
            continue
        for exp in expects:
            out.append((module, step, exp))
    return out


def matrix_to_md(
    *,
    workbook_name: str,
    workbook_url: str,
    sheet_name: str,
    matrix: List[List[Any]],
    export_date: str,
) -> Tuple[str, int]:
    _, cases, _ = iter_cases_from_matrix(matrix, sheet_name)
    if not cases:
        return "", 0

    by_module: Dict[str, List[CaseRow]] = defaultdict(list)
    for case in cases:
        if _should_filter_noise(case.module, case.step):
            continue
        mod = case.module or "未分类"
        by_module[mod].append(case)

    lines: List[str] = [
        f"# {_workbook_stem(workbook_name)}",
        "",
        f"- 钉钉源 URL: {workbook_url}",
        f"- Sheet: {sheet_name}",
        f"- 导出时间: {export_date}",
        "- 表头映射: 功能模块 / 用例步骤描述 / 预期结果（自动识别）",
        "",
    ]

    row_count = 0
    for module in sorted(by_module.keys(), key=lambda x: (x == "未分类", x)):
        module_cases = by_module[module]
        if _is_shell_module(module, module_cases):
            continue
        expanded = _expand_rows(module_cases)
        if not expanded:
            continue
        lines.append(f"## 功能模块：{module}")
        lines.append("")
        lines.append("| 功能模块 | 用例步骤描述 | 预期结果 |")
        lines.append("|---------|------------|---------|")
        for mod, step, exp in expanded:
            lines.append(
                f"| {_escape_cell(mod)} | {_escape_cell(step)} | {_escape_cell(exp)} |"
            )
            row_count += 1
        lines.append("")

    if row_count == 0:
        return "", 0
    return "\n".join(lines).rstrip() + "\n", row_count


def list_spreadsheets(folder_url: str) -> List[Tuple[str, str]]:
    cookie = resolve_dingtalk_cookie()
    folder_id = extract_node_id_from_url(folder_url)
    children = list_folder_children_via_box(folder_id, cookie=cookie)
    items: List[Tuple[str, str]] = []
    for entry in children:
        if not is_spreadsheet_entry(entry):
            continue
        name = str(entry.get("name") or "").strip()
        node_id = str(entry.get("dentryUuid") or "").strip()
        if not name or not node_id:
            continue
        items.append((name, f"https://alidocs.dingtalk.com/i/nodes/{node_id}"))
    return items


def output_filename(workbook_name: str, sheet_name: str, *, multi_sheet: bool) -> str:
    wb = _workbook_stem(workbook_name)
    sh = _safe_filename(sheet_name)
    if multi_sheet:
        return f"{wb}_{sh}.md"
    return f"{wb}.md"


def process_workbook(
    wb_name: str,
    wb_url: str,
    out_dir: Path,
    export_date: str,
) -> List[dict]:
    manifest: List[dict] = []
    print(f"\n=== {wb_name} ===")
    try:
        sheets = fetch_workbook_sheets(wb_url)
    except Exception as exc:
        print(f"  读取失败: {exc}")
        manifest.append({"workbook": wb_name, "url": wb_url, "status": "error", "error": str(exc)})
        return manifest

    multi = len(sheets) > 1
    for sheet_name, matrix in sheets:
        md_text, rows = matrix_to_md(
            workbook_name=wb_name,
            workbook_url=wb_url,
            sheet_name=sheet_name,
            matrix=matrix,
            export_date=export_date,
        )
        fname = output_filename(wb_name, sheet_name, multi_sheet=multi)
        if rows == 0:
            print(f"  跳过 sheet（无用例行）: {sheet_name}")
            manifest.append(
                {
                    "workbook": wb_name,
                    "sheet": sheet_name,
                    "file": fname,
                    "status": "skipped",
                    "reason": "no valid cases",
                }
            )
            continue
        out_path = out_dir / fname
        out_path.write_text(md_text, encoding="utf-8")
        print(f"  已写入 {fname} ({rows} 行)")
        manifest.append(
            {
                "workbook": wb_name,
                "sheet": sheet_name,
                "file": fname,
                "status": "ok",
                "rows": rows,
                "url": wb_url,
            }
        )
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="钉钉目录 Excel → Markdown")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--folder-url", help="钉钉文件夹 URL")
    src.add_argument("--workbook-url", help="单个钉钉 Excel URL")
    ap.add_argument("--workbook-name", default="", help="单表导出时的文件名（默认从 URL 推断）")
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=_ROOT / "2026活动",
        help="输出目录（默认项目根 2026活动/）",
    )
    ap.add_argument("--skip-name", action="append", default=[], help="跳过文件名包含的关键词")
    args = ap.parse_args()

    out_dir = args.output_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    export_date = date.today().isoformat()

    if args.workbook_url:
        wb_url = args.workbook_url.strip()
        wb_name = (args.workbook_name or "").strip() or f"{_workbook_stem(wb_url)}.axls"
        spreadsheets = [(wb_name, wb_url)]
    else:
        spreadsheets = list_spreadsheets(args.folder_url.strip())
        if not spreadsheets:
            raise SystemExit("目录下未发现 Excel 表格")

    skip_tokens = [s for s in args.skip_name if s]
    manifest: List[dict] = []

    for wb_name, wb_url in spreadsheets:
        if skip_tokens and any(tok in wb_name for tok in skip_tokens):
            print(f"跳过: {wb_name}")
            continue
        manifest.extend(process_workbook(wb_name, wb_url, out_dir, export_date))

    manifest_path = out_dir / "_manifest.json"
    import json

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for m in manifest if m.get("status") == "ok")
    print(f"\n完成：{ok} 个文件写入 {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
