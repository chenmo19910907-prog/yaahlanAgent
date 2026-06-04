#!/usr/bin/env python3
"""对比 PRD 模块清单与用例 Markdown 中的功能模块覆盖。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from check_testcase_md import _col_index, _parse_table, MODULE_COL_NAMES
from kb_index import match_module_keys

ROOT = Path(__file__).resolve().parent.parent


def _modules_from_testcase(path: Path) -> set[str]:
    table = _parse_table(path.read_text(encoding="utf-8").splitlines())
    if not table:
        return set()
    mod_i = _col_index(table.headers, MODULE_COL_NAMES)
    if mod_i is None:
        return set()
    out: set[str] = set()
    for row in table.rows:
        if mod_i < len(row):
            val = row[mod_i].strip()
            if val:
                out.add(val)
    return out


def _normalize(name: str) -> str:
    return name.strip().lower().replace(" ", "")


def _match_expected(expected: str, modules: set[str]) -> bool:
    exp_norm = _normalize(expected)
    for mod in modules:
        if exp_norm in _normalize(mod) or _normalize(mod) in exp_norm:
            return True
    keys = match_module_keys(expected)
    if not keys:
        return False
    for mod in modules:
        if any(kw in mod for kw in ("礼物", "榜单", "房间", "动态", "vip", "公会")):
            for key in keys:
                if key in ("gift", "rank_activity", "room", "moments", "vip", "agency"):
                    return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="PRD 模块清单 vs 用例功能模块覆盖 diff")
    parser.add_argument("--modules-file", type=Path, required=True, help="每行一个 PRD 模块名")
    parser.add_argument("--testcase", type=Path, required=True, help="用例 .md 路径")
    args = parser.parse_args()

    mod_file = args.modules_file.expanduser()
    case_file = args.testcase.expanduser()
    if not mod_file.is_file():
        print(f"找不到模块清单: {mod_file}", file=sys.stderr)
        return 1
    if not case_file.is_file():
        print(f"找不到用例文件: {case_file}", file=sys.stderr)
        return 1

    expected = [
        ln.strip()
        for ln in mod_file.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    modules = _modules_from_testcase(case_file)

    missing = [e for e in expected if not _match_expected(e, modules)]
    extra = sorted(modules)

    print(f"PRD 模块数: {len(expected)}")
    print(f"用例功能模块（非空）: {len(modules)}")
    print()

    if missing:
        print("可能未覆盖（请人工核对）:")
        for m in missing:
            print(f"  - {m}")
    else:
        print("清单内模块均已匹配到用例中的功能模块（模糊匹配）")

    print("\n用例中的功能模块:")
    for m in extra:
        print(f"  - {m}")

    if missing:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
