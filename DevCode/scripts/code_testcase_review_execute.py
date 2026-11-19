#!/usr/bin/env python3
"""
代码×用例审查：钉钉表安全读/写（fail 标注、末尾补用例）。

用法：
  python3 DevCode/scripts/code_testcase_review_execute.py sheet-info --url <alidocs> --sheet <名称>
  python3 DevCode/scripts/code_testcase_review_execute.py mark-fail --url ... --sheet ... --items fails.json
  python3 DevCode/scripts/code_testcase_review_execute.py append-cases --url ... --sheet ... --cases cases.json

fails.json: [{"row": 43, "reason": "..."}, ...]
cases.json: [["编号","模块","步骤","预期"], ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = REPO / ".cursor/skills/code-testcase-review/scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

from dingtalk_sheet import (  # noqa: E402
    detect_case_start_row,
    extract_sheet_git_context,
    find_last_case_row_from_values,
    find_sheet_id_sync,
    get_token_sync,
    mark_fail_sync,
    protected_row_end,
    read_range_sync,
    workbook_id_from_url,
    write_range_sync,
)


def _resolve_sheet(url: str, sheet: str) -> tuple[str, str, str, str]:
    wb = workbook_id_from_url(url)
    token, op = get_token_sync()
    sid = find_sheet_id_sync(token, op, wb, sheet)
    if not sid:
        raise SystemExit(f"未找到 Sheet: {sheet!r}")
    return wb, sid, token, op


def cmd_sheet_info(url: str, sheet: str) -> int:
    wb, sid, token, op = _resolve_sheet(url, sheet)
    values = read_range_sync(token, op, wb, sid, "A1:D850")
    ctx = extract_sheet_git_context(values)
    last = find_last_case_row_from_values(values)
    payload = {
        "workbook_id": wb,
        "sheet_id": sid,
        "case_start_row": ctx["case_start_row"],
        "protected_end_row": ctx["protected_end_row"],
        "last_case_row": last,
        "append_start_row": max(last + 1, ctx["protected_end_row"] + 1),
        "repos": ctx["repos"],
        "requirement_branches": ctx["requirement_branches"],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_mark_fail(url: str, sheet: str, items_path: Path) -> int:
    wb, sid, token, op = _resolve_sheet(url, sheet)
    raw = json.loads(items_path.read_text(encoding="utf-8"))
    items: list[tuple[int, str]] = []
    for it in raw:
        row = int(it["row"])
        reason = str(it.get("reason") or "")
        if row < detect_case_start_row(read_range_sync(token, op, wb, sid, "A1:D30")):
            raise SystemExit(f"行 {row} 位于用例区之前，拒绝标注")
        items.append((row, reason))
    mark_fail_sync(token, op, wb, sid, items)
    print(json.dumps({"marked": len(items)}, ensure_ascii=False))
    return 0


def cmd_append_cases(url: str, sheet: str, cases_path: Path) -> int:
    wb, sid, token, op = _resolve_sheet(url, sheet)
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise SystemExit("cases.json 须为非空二维数组")
    values = read_range_sync(token, op, wb, sid, "A1:D800")
    protected = protected_row_end(values)
    last = find_last_case_row_from_values(values)
    start = max(last + 1, protected + 1)
    status = write_range_sync(
        token, op, wb, sid, cases, start, "A", protected_end_row=protected
    )
    verify = read_range_sync(
        token, op, wb, sid, f"A{start}:D{start + len(cases) - 1}"
    )
    print(
        json.dumps(
            {"append_start_row": start, "count": len(cases), "http_status": status, "verify": verify},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="代码×用例审查 · 钉钉表 IO")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_info = sub.add_parser("sheet-info", help="解析表布局、仓库分支、补写起始行")
    p_info.add_argument("--url", required=True)
    p_info.add_argument("--sheet", required=True)

    p_fail = sub.add_parser("mark-fail", help="批量写 E/F")
    p_fail.add_argument("--url", required=True)
    p_fail.add_argument("--sheet", required=True)
    p_fail.add_argument("--items", type=Path, required=True)

    p_app = sub.add_parser("append-cases", help="表末追加 A–D")
    p_app.add_argument("--url", required=True)
    p_app.add_argument("--sheet", required=True)
    p_app.add_argument("--cases", type=Path, required=True)

    args = parser.parse_args()
    if args.cmd == "sheet-info":
        return cmd_sheet_info(args.url, args.sheet)
    if args.cmd == "mark-fail":
        return cmd_mark_fail(args.url, args.sheet, args.items)
    if args.cmd == "append-cases":
        return cmd_append_cases(args.url, args.sheet, args.cases)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
