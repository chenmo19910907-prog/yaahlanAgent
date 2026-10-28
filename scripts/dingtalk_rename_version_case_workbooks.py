#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为 2.5.0 之后缺括号后缀的版本用例表补全「（功能概况…）」文件名。"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from dingtalk_kb_source import (  # noqa: E402
    DingtalkWorkbook,
    discover_workbooks,
    extract_node_id_from_url,
    resolve_dingtalk_cookie,
    resolve_folder_url,
)
from version_case_workbook_naming import (  # noqa: E402
    apply_workbook_filename_extension,
    compute_version_case_workbook_title,
    parse_version_tuple,
    proposed_workbook_title,
    workbook_name_has_feature_suffix,
    workbook_title_base_for_compare,
)


def _ensure_paths() -> None:
    gw = _ROOT / "platform" / "dingtalk_gateway"
    if str(gw) not in sys.path:
        sys.path.insert(0, str(gw))


async def _sheet_names_and_sheet1_top(
    url: str,
    *,
    cookie: str | None = None,
) -> tuple[list[str], list[list[object]]]:
    from alidocs_axls_cookie_read import fetch_workbook_sheets_via_cookie  # noqa: E402

    try:
        names, sheet1_rows = await fetch_workbook_sheets_via_cookie(url, cookie=cookie)
        return names, sheet1_rows
    except Exception:
        pass

    _ensure_paths()
    report_root = _ROOT / "Report"
    if str(report_root) not in sys.path:
        sys.path.insert(0, str(report_root))
    from report.dingtalk_xlsx import fetch_workbook_sheets  # noqa: E402

    sheets = await fetch_workbook_sheets(url)
    names = [n for n, _ in sheets]
    sheet1_rows: list[list[object]] = []
    for name, rows in sheets:
        if name.strip() in ("Sheet1", "sheet1") or name.lower() == "sheet1":
            sheet1_rows = rows[:40] if rows else []
            break
    if not sheet1_rows and sheets:
        sheet1_rows = sheets[0][1][:40]
    return names, sheet1_rows


def main() -> int:
    ap = argparse.ArgumentParser(description="补全版本用例钉钉文档名中的功能概况括号")
    ap.add_argument("--folder-id", default="yaahlan-testcases", help="DingTalk/config/folders.json 中的 id")
    ap.add_argument("--after-version", default="2.5.0", help="仅处理严格大于该版本的表（默认 2.5.0 → 从 2.5.1 起）")
    ap.add_argument("--dry-run", action="store_true", help="只预览，不重命名")
    ap.add_argument("--limit", type=int, default=0, help="最多处理 N 个（0=不限）")
    ap.add_argument(
        "--resimplify",
        action="store_true",
        help="已带括号的版本用例也按当前 sheet 重新生成简化概况并改名",
    )
    args = ap.parse_args()
    _ensure_paths()

    after = parse_version_tuple(f"{args.after_version}版本用例")
    if not after:
        raise SystemExit(f"无效 --after-version: {args.after_version}")

    folder_url, _entry = resolve_folder_url(folder_id=args.folder_id)
    dingtalk_cookie = resolve_dingtalk_cookie()

    workbooks = discover_workbooks(folder_url, recursive=True)
    targets: list[DingtalkWorkbook] = []
    for wb in workbooks:
        ver = wb.version_tuple
        if ver <= after:
            continue
        if workbook_name_has_feature_suffix(wb.name) and not args.resimplify:
            continue
        targets.append(wb)

    targets.sort(key=lambda w: w.version_tuple, reverse=True)
    if args.limit > 0:
        targets = targets[: args.limit]

    if not targets:
        print("无需重命名的版本用例表（无 >2.5.0 且缺括号/待简化的项）")
        return 0

    renamed = 0
    for wb in targets:
        try:
            sheet_names, sheet1_rows = asyncio.run(
                _sheet_names_and_sheet1_top(wb.url, cookie=dingtalk_cookie)
            )
        except Exception as exc:
            print(f"跳过 {wb.name}: 读取 sheet 失败 — {exc}", file=sys.stderr)
            continue
        if args.resimplify:
            new_title = compute_version_case_workbook_title(
                wb.name,
                sheet_names=sheet_names,
                sheet1_rows=sheet1_rows,
            )
        else:
            new_title = proposed_workbook_title(
                wb.name,
                sheet_names=sheet_names,
                sheet1_rows=sheet1_rows,
            )
        if not new_title:
            print(f"跳过 {wb.name}: 无功能概况/需求 sheet，不写入空括号")
            continue
        new_title = apply_workbook_filename_extension(wb.name, new_title)
        if workbook_title_base_for_compare(new_title) == workbook_title_base_for_compare(wb.name):
            print(f"跳过 {wb.name}: 标题未变化")
            continue
        print(f"{wb.version_label}  {wb.name}\n  → {new_title}\n")
        if args.dry_run:
            renamed += 1
            continue
        node_id = extract_node_id_from_url(wb.url)
        try:
            from alidocs_excel_export import rename_dentry_via_box_api  # noqa: E402

            rename_dentry_via_box_api(node_id, new_title, cookie=dingtalk_cookie)
            renamed += 1
        except Exception as exc:
            print(f"失败 {wb.name}: {exc}", file=sys.stderr)

    print(f"{'预览' if args.dry_run else '完成'} {renamed}/{len(targets)} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
