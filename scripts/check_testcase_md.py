#!/usr/bin/env python3
"""校验 temporary_testcase 或指定 Markdown 用例表的格式与基本质量。"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from project_paths import temporary_testcase_dir  # noqa: E402

DEFAULT_DIR = temporary_testcase_dir()

STEP_COL_NAMES = frozenset({"测试步骤", "步骤"})
EXPECT_COL_NAMES = frozenset({"预期结果", "期望结果", "预期"})
MODULE_COL_NAMES = frozenset({"功能模块", "模块"})
ID_COL_NAMES = frozenset({"编号", "用例id", "用例ID"})


@dataclass
class Issue:
    level: str  # ERROR | WARN
    row: int
    message: str


@dataclass
class TableData:
    headers: list[str]
    rows: list[list[str]] = field(default_factory=list)


def _norm_header(cell: str) -> str:
    return cell.strip().replace(" ", "")


def _parse_table(lines: list[str]) -> TableData | None:
    table_lines = [ln for ln in lines if ln.strip().startswith("|")]
    if len(table_lines) < 2:
        return None
    rows_raw: list[list[str]] = []
    for ln in table_lines:
        parts = [p.strip() for p in ln.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-+:?", p.replace(" ", "")) for p in parts if p):
            continue
        rows_raw.append(parts)
    if not rows_raw:
        return None
    headers = [_norm_header(h) for h in rows_raw[0]]
    body = rows_raw[1:]
    return TableData(headers=headers, rows=body)


def _col_index(headers: list[str], names: frozenset[str]) -> int | None:
    for i, h in enumerate(headers):
        if h in names or h.lower() in {n.lower() for n in names}:
            return i
    return None


def _cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return row[idx].strip()


def validate_table(table: TableData, *, source: str) -> list[Issue]:
    issues: list[Issue] = []
    mod_i = _col_index(table.headers, MODULE_COL_NAMES)
    step_i = _col_index(table.headers, STEP_COL_NAMES)
    exp_i = _col_index(table.headers, EXPECT_COL_NAMES)
    id_i = _col_index(table.headers, ID_COL_NAMES)

    if step_i is None or exp_i is None:
        issues.append(
            Issue("ERROR", 0, f"{source}: 表格须含「测试步骤」与「预期结果/期望结果」列")
        )
        return issues

    seen_ids: dict[str, int] = {}
    last_step = ""
    last_module = ""
    module_values: list[str] = []

    for r_idx, row in enumerate(table.rows, start=2):
        module = _cell(row, mod_i)
        step = _cell(row, step_i)
        expect = _cell(row, exp_i)
        case_id = _cell(row, id_i)

        if module:
            last_module = module
            module_values.append(module)
            if " - " in module or "－" in module:
                issues.append(
                    Issue(
                        "WARN",
                        r_idx,
                        "功能模块列含「-」说明，建议只写模块名，细节放入测试步骤",
                    )
                )

        if case_id:
            prev = seen_ids.get(case_id)
            if prev is not None:
                issues.append(
                    Issue("WARN", r_idx, f"用例编号重复: {case_id}（首见于第 {prev} 行）")
                )
            else:
                seen_ids[case_id] = r_idx

        if step:
            last_step = step
            if not expect:
                issues.append(Issue("ERROR", r_idx, "有测试步骤但预期结果为空"))
            if len(step) < 4:
                issues.append(Issue("WARN", r_idx, "测试步骤过短，建议写可执行操作"))
            continue

        # 续行：多预期
        if expect and last_step:
            continue
        if expect and not last_step:
            issues.append(
                Issue(
                    "ERROR",
                    r_idx,
                    "续行预期缺少前置测试步骤（上一行须有非空测试步骤）",
                )
            )
            continue
        if not step and not expect:
            issues.append(Issue("WARN", r_idx, "空行或步骤与预期均为空"))
        elif not step and expect and not last_module:
            issues.append(Issue("WARN", r_idx, "仅有预期、无模块与步骤上下文"))

    if len(table.rows) == 0:
        issues.append(Issue("ERROR", 0, f"{source}: 表格无数据行"))
    elif len(table.rows) < 5:
        issues.append(Issue("WARN", 0, f"{source}: 用例仅 {len(table.rows)} 条，偏少请确认是否漏模块"))

    unique_modules = {m.split("-")[0].split("】")[-1] for m in module_values if m}
    if not module_values and len(table.rows) > 0:
        issues.append(Issue("WARN", 0, f"{source}: 功能模块列全为空，不利于覆盖核对"))

    return issues


def check_file(path: Path) -> list[Issue]:
    text = path.read_text(encoding="utf-8")
    table = _parse_table(text.splitlines())
    if table is None:
        return [Issue("ERROR", 0, f"{path.name}: 未找到 Markdown 表格")]
    return validate_table(table, source=path.name)


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 Markdown 测试用例表")
    parser.add_argument(
        "paths",
        nargs="*",
        help="用例 .md 路径；默认扫描 temporary_testcase/*.md",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_DIR,
        help=f"扫描目录（默认 {DEFAULT_DIR.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="存在 WARN 时也返回非 0",
    )
    args = parser.parse_args()

    files: list[Path] = []
    if args.paths:
        for p in args.paths:
            path = Path(p).expanduser()
            if path.is_dir():
                files.extend(sorted(path.glob("*.md")))
            elif path.is_file():
                files.append(path)
    else:
        d = args.dir.expanduser()
        if not d.is_dir():
            print(f"目录不存在: {d}", file=sys.stderr)
            return 1
        files = sorted(d.glob("*.md"))

    if not files:
        print("未找到待校验的 .md 文件", file=sys.stderr)
        return 1

    all_issues: list[tuple[Path, list[Issue]]] = []
    for f in files:
        all_issues.append((f, check_file(f)))

    errors = 0
    warns = 0
    for path, issues in all_issues:
        if not issues:
            print(f"OK  {path.name}")
            continue
        print(f"\n--- {path.name} ---")
        for item in issues:
            print(f"  [{item.level}] L{item.row}: {item.message}")
            if item.level == "ERROR":
                errors += 1
            else:
                warns += 1

    print(f"\n合计: {len(files)} 个文件, ERROR={errors}, WARN={warns}")
    if errors:
        return 1
    if args.strict and warns:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
