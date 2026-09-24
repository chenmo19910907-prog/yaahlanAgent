"""算薪 pytest 套件统一 CLI（供 Agent / 工具平台调用）。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .paths import salary_dir

SUITES: dict[str, dict[str, str]] = {
    "cycle": {
        "label": "半月结算薪",
        "test": "business_case/salary/cycle_salary/test_yaahlan_cycle_salary.py",
        "cases_json": "data/salary/cycle_salary/yaahlan_cycle_salary_cases.json",
    },
    "exempt": {
        "label": "主播豁免专项",
        "test": "business_case/salary/cycle_salary/test_yaahlan_cycle_salary_exempt.py",
        "cases_json": "data/salary/cycle_salary/yaahlan_cycle_salary_exempt_suite.json",
    },
    "guild-progress": {
        "label": "公会进步奖",
        "test": "business_case/salary/guild_progress_award/test_yaahlan_guild_progress_award.py",
        "cases_json": "data/salary/guild_progress_award/yaahlan_guild_progress_award_cases.json",
    },
    "refund-blacklist": {
        "label": "退款黑名单算薪",
        "test": "business_case/salary/refund_blacklist/test_yaahlan_refund_blacklist_salary.py",
        "cases_json": "data/salary/refund_blacklist/yaahlan_refund_blacklist_salary_cases.json",
    },
    "confirm": {
        "label": "确认应得薪资（写操作）",
        "test": "business_case/salary/confirm_salary/test_yaahlan_confirm_salary.py",
        "cases_json": "data/salary/confirm_salary/yaahlan_confirm_salary_cases.json",
    },
}


def _run(cmd: list[str], *, cwd: str, env: dict[str, str] | None = None) -> int:
    print("$", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=cwd, env=env)


def _python_cmd() -> str:
    venv_py = os.path.join(salary_dir(), ".venv", "bin", "python3")
    if os.path.isfile(venv_py):
        return venv_py
    return sys.executable


def _load_env(base: str) -> dict[str, str]:
    env = os.environ.copy()
    env_path = os.path.join(base, ".env")
    if not os.path.isfile(env_path):
        return env
    with open(env_path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip())
    return env


def _pytest_base(env: dict[str, str]) -> list[str]:
    return [_python_cmd(), "-m", "pytest"]


def cmd_check_env(_: argparse.Namespace) -> int:
    script = os.path.join(salary_dir(), "scripts", "check_env.py")
    return _run([_python_cmd(), script], cwd=salary_dir())


def cmd_list_suites(_: argparse.Namespace) -> int:
    rows: list[dict[str, Any]] = []
    for key, meta in SUITES.items():
        rows.append(
            {
                "id": key,
                "label": meta["label"],
                "test": meta["test"],
                "cases_json": meta["cases_json"],
            }
        )
    print(json.dumps({"suites": rows}, ensure_ascii=False, indent=2))
    return 0


def cmd_list_cases(args: argparse.Namespace) -> int:
    suite = SUITES.get(args.suite)
    if not suite:
        print(f"未知套件: {args.suite}", file=sys.stderr)
        return 2
    path = os.path.join(salary_dir(), suite["cases_json"])
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    cases = data.get("cases") or data.get("smoke_cases") or []
    if isinstance(cases, list) and cases and isinstance(cases[0], str):
        names = cases
    else:
        names = [c.get("case_name", "") for c in cases if isinstance(c, dict)]
    print(json.dumps({"suite": args.suite, "count": len(names), "cases": names}, ensure_ascii=False, indent=2))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    suite = SUITES.get(args.suite)
    if not suite:
        print(f"未知套件: {args.suite}", file=sys.stderr)
        return 2

    base = salary_dir()
    env = _load_env(base)
    cmd = _pytest_base(env)
    cmd.append(suite["test"])

    if args.case:
        cmd.extend(["-k", args.case])
    elif args.smoke:
        if args.suite == "cycle":
            script = os.path.join(base, "scripts", "run_cycle_salary_smoke.sh")
            extra = list(args.pytest_args or [])
            if args.verbose and "-v" not in extra:
                extra.append("-v")
            return _run(["bash", script, *extra], cwd=base, env=env)
        if args.suite == "exempt":
            script = os.path.join(base, "scripts", "run_cycle_salary_exempt_smoke.sh")
            extra = list(args.pytest_args or [])
            if args.verbose and "-v" not in extra:
                extra.append("-v")
            return _run(["bash", script, *extra], cwd=base, env=env)
        print("该套件未定义 --smoke 预设，请用 --case 指定", file=sys.stderr)
        return 2

    if args.report:
        env["GENERATE_SALARY_REPORT"] = "1"
        cmd.append("--salary-report")
        if args.suite == "exempt":
            env["CYCLE_SALARY_SUITE"] = "exempt"
            cmd.extend(["--salary-report-suite", "exempt"])

    if args.guild_progress_policy:
        cmd.extend(["--guild-progress-policy", args.guild_progress_policy])

    if args.suite == "confirm":
        if env.get("RUN_CONFIRM_BY_AREA", "").strip().lower() not in ("1", "true", "yes"):
            print(
                "确认应得薪资为写操作，须先设置 RUN_CONFIRM_BY_AREA=1 且配置 CMS 凭证",
                file=sys.stderr,
            )
            return 2

    if args.pytest_args:
        cmd.extend(args.pytest_args)

    if args.verbose and "-v" not in cmd:
        cmd.append("-v")

    return _run(cmd, cwd=base, env=env)


def cmd_cc_config(args: argparse.Namespace) -> int:
    script = os.path.join(salary_dir(), "utils", "cc_config.py")
    cmd = [_python_cmd(), script]
    if args.key:
        cmd.append(args.key)
    return _run(cmd, cwd=salary_dir())


def cmd_dashboard(_: argparse.Namespace) -> int:
    script = os.path.join(salary_dir(), "scripts", "run_web_dashboard.sh")
    return _run(["bash", script], cwd=salary_dir())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Yaahlan 算薪专项自动化测试（pytest 数据驱动 E2E）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check-env", help="检查 Python/MySQL/依赖是否就绪").set_defaults(handler=cmd_check_env)
    sub.add_parser("list-suites", help="列出可执行套件").set_defaults(handler=cmd_list_suites)

    p_cases = sub.add_parser("list-cases", help="列出套件内用例名")
    p_cases.add_argument("suite", choices=sorted(SUITES.keys()))
    p_cases.set_defaults(handler=cmd_list_cases)

    p_run = sub.add_parser("run", help="执行指定套件")
    p_run.add_argument("suite", choices=sorted(SUITES.keys()))
    p_run.add_argument("--smoke", action="store_true", help="跑冒烟子集（cycle/exempt）")
    p_run.add_argument("--report", action="store_true", help="执行后生成 MD/HTML 报告并可选发钉钉")
    p_run.add_argument("--case", help="pytest -k 过滤单个/多个用例名")
    p_run.add_argument(
        "--guild-progress-policy",
        choices=("202512", "202608", "auto"),
        help="公会进步奖政策口径",
    )
    p_run.add_argument("-v", "--verbose", action="store_true")
    p_run.add_argument(
        "pytest_args",
        nargs="*",
        default=[],
        help="透传 pytest 额外参数（放在命令末尾，如 --maxfail=1）",
    )
    p_run.set_defaults(handler=cmd_run)

    p_cc = sub.add_parser("cc-config", help="读盘古配置中心（公会激励开关等）")
    p_cc.add_argument("key", nargs="?", default="", help="配置 key，默认 tradeMotivationMaxCycleSwitch")
    p_cc.set_defaults(handler=cmd_cc_config)

    sub.add_parser("dashboard", help="启动可视化测试后台 :8088").set_defaults(handler=cmd_dashboard)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))
