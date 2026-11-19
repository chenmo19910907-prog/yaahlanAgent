#!/usr/bin/env python3
"""校验 code-testcase-review dingtalk_sheet：B7 覆盖率行 C/D 分支解析。"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = REPO / ".cursor/skills/code-testcase-review/scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

from dingtalk_sheet import (  # noqa: E402
    COVERAGE_QUALITY_PLATFORM_B7,
    detect_case_start_row,
    extract_b7_requirement_branches,
    extract_coverage_platform_repos,
    extract_repo_info,
    extract_sheet_git_context,
    find_last_case_row_from_values,
    protected_row_end,
)


def _assert_eq(label: str, got, want) -> None:
    if got != want:
        raise AssertionError(f"{label}: got {got!r}, want {want!r}")


def main() -> int:
    blank = [[""] * 5 for _ in range(6)]
    row7 = ["", COVERAGE_QUALITY_PLATFORM_B7, "服务端voga-mts-user", "feature/foo", "仓库：voga-mts-user"]
    row8 = ["", COVERAGE_QUALITY_PLATFORM_B7, "前端 yaahlan-h5-vip", "feature/bar", ""]
    values = blank + [row7, row8]

    _assert_eq("b7 branches", extract_b7_requirement_branches(values), ["feature/foo", "feature/bar"])
    ctx = extract_sheet_git_context(values)
    _assert_eq("requirement_branches", ctx["requirement_branches"], ["feature/foo", "feature/bar"])
    repos = extract_repo_info(values)
    _assert_eq("repo count", len(repos), 2)
    _assert_eq("user branch", repos[0].get("branch"), "feature/foo")

    no_b7 = blank + [["", "其他模块", "分支：feature/x", "", ""]]
    _assert_eq("ignore wrong B7", extract_b7_requirement_branches(no_b7), [])

    empty_cd = blank + [["", COVERAGE_QUALITY_PLATFORM_B7, "", "", ""]]
    _assert_eq("empty C/D", extract_b7_requirement_branches(empty_cd), [])

    header = ["用例编号", "功能模块", "case步骤描述", "预期结果", ""]
    cov1 = ["", COVERAGE_QUALITY_PLATFORM_B7, "服务端voga-mts-user，voga-mts-components", "feature/vip", ""]
    cov2 = ["", COVERAGE_QUALITY_PLATFORM_B7, "前端 yaahlan-h5-vip", "dev", ""]
    case1 = ["", "【模块】", "步骤1", "预期1", ""]
    vip = [[""] * 5 for _ in range(5)] + [header, cov1, cov2, case1]
    _assert_eq("case_start", detect_case_start_row(vip), 9)
    _assert_eq("protected_end", protected_row_end(vip), 8)
    _assert_eq("last_case", find_last_case_row_from_values(vip), 9)
    repos_cov = extract_coverage_platform_repos(vip)
    _assert_eq("cov repo count", len(repos_cov), 3)
    _assert_eq("cov user branch", repos_cov[0]["branch"], "feature/vip")

    print("verify_code_testcase_sheet_parse: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
