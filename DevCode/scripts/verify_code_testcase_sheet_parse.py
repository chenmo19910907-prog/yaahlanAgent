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
    extract_b7_requirement_branches,
    extract_repo_info,
    extract_sheet_git_context,
)


def _assert_eq(label: str, got, want) -> None:
    if got != want:
        raise AssertionError(f"{label}: got {got!r}, want {want!r}")


def main() -> int:
    blank = [[""] * 5 for _ in range(6)]
    row7 = ["", COVERAGE_QUALITY_PLATFORM_B7, "feature/foo", "feature/bar", "仓库：voga-mts-user"]
    values = blank + [row7]

    _assert_eq("b7 branches", extract_b7_requirement_branches(values), ["feature/foo", "feature/bar"])
    ctx = extract_sheet_git_context(values)
    _assert_eq("requirement_branches", ctx["requirement_branches"], ["feature/foo", "feature/bar"])
    repos = extract_repo_info(values)
    _assert_eq("repo count", len(repos), 1)
    _assert_eq("merged branch", repos[0].get("branch"), "feature/foo")

    no_b7 = blank + [["", "其他模块", "分支：feature/x", "", ""]]
    _assert_eq("ignore wrong B7", extract_b7_requirement_branches(no_b7), [])

    empty_cd = blank + [["", COVERAGE_QUALITY_PLATFORM_B7, "", "", ""]]
    _assert_eq("empty C/D", extract_b7_requirement_branches(empty_cd), [])

    print("verify_code_testcase_sheet_parse: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
