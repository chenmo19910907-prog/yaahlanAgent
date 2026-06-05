#!/usr/bin/env python3
"""一键同步 bug-kb / online-kb（路径可通过参数或环境变量覆盖）。"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _run(script: str, extra: list[str]) -> int:
    cmd = [sys.executable, str(SCRIPTS / script), *extra]
    print(f"\n>> {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="批量同步知识库")
    parser.add_argument(
        "--regression-xlsx",
        default=os.environ.get(
            "YAAHLAN_REGRESSION_XLSX",
            str(Path.home() / "Desktop" / "发版回归case.xlsx"),
        ),
        help="发版回归 xlsx",
    )
    parser.add_argument(
        "--tasks-xlsx",
        default=os.environ.get(
            "YAAHLAN_TASKS_XLSX",
            str(
                Path.home()
                / "Desktop"
                / "【yaahlan】任务信息表_20260529 15.37.14.xlsx"
            ),
        ),
        help="任务信息表 xlsx（bug-kb + online-kb）",
    )
    parser.add_argument(
        "--with-regression",
        action="store_true",
        help="额外同步发版回归 xlsx → regression-kb/（目录已移除时勿用）",
    )
    parser.add_argument(
        "--skip-bug",
        action="store_true",
    )
    parser.add_argument(
        "--skip-online",
        action="store_true",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将执行的命令",
    )
    args = parser.parse_args()

    steps: list[tuple[str, list[str]]] = []
    if args.with_regression:
        steps.append(
            (
                "regression_kb_from_xlsx.py",
                ["--xlsx", args.regression_xlsx],
            )
        )
    if not args.skip_bug:
        steps.append(
            (
                "bug_kb_from_tasks_xlsx.py",
                ["--source", args.tasks_xlsx],
            )
        )
    if not args.skip_online:
        steps.append(
            (
                "online_kb_from_tasks_xlsx.py",
                ["--source", args.tasks_xlsx],
            )
        )

    if args.dry_run:
        for script, extra in steps:
            print(f"python3 scripts/{script} {' '.join(extra)}")
        return 0

    rc = 0
    for script, extra in steps:
        path_arg = extra[-1]
        if script != "regression_kb_from_xlsx.py":
            key = "--source"
        else:
            key = "--xlsx"
        p = Path(path_arg).expanduser()
        if not p.is_file():
            print(f"跳过 {script}: 找不到 {key}={p}", file=sys.stderr)
            rc = 1
            continue
        if _run(script, extra) != 0:
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
