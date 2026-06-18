"""E2E CLI。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .budget import StepBudget
from .case_model import load_case, resolve_case_path
from .env import load_local_env
from .kb import load_kb_hints
from .step_hints import case_modules
from .loop_cycle import run_step_cycle
from .paths import cases_dir, config_path, e2e_dir, reports_dir
from .perceive import perceive_for_step, screen_summary
from .runner import run_case


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="E2E：知识库 + MOA/Tunnel + 视觉反馈的自然语言安卓自动化（识别→思考→执行）",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("doctor", help="检查目录与配置是否就绪")
    sub.add_parser("list", help="列出 cases/ 下用例")

    run = sub.add_parser("run", help="按用例执行完整三步循环")
    run.add_argument("--case", required=True, help="用例 id 或 cases/ 下 JSON 路径")
    run.add_argument("--dry-run", action="store_true", help="仅规划步骤，不操作真机")
    run.add_argument("--max-steps", type=int, help="最多执行几步（调试）")

    cycle = sub.add_parser("cycle", help="单步：识别 → 思考 → 执行")
    cycle.add_argument("--step", required=True, help="自然语言步骤，如「点击手机号登录」")
    cycle.add_argument("--case", help="可选：加载用例 account/module 上下文")
    cycle.add_argument("--image", action="store_true", help="识别时附带截图（WebView）")

    perceive = sub.add_parser("perceive", help="仅识别：输出 observe 摘要 JSON")
    perceive.add_argument("--image", action="store_true", help="附带截图")

    return parser


def _load_config() -> dict:
    path = config_path()
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _cmd_doctor() -> int:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("e2e 目录", e2e_dir().is_dir(), str(e2e_dir())))
    checks.append(("config.json", config_path().is_file(), str(config_path())))
    checks.append(("cases/", cases_dir().is_dir(), str(cases_dir())))
    checks.append(("reports/", reports_dir().is_dir(), str(reports_dir())))
    adb_entry = e2e_dir().parent / "adb" / "adb_execute.py"
    checks.append(("adb 桥接", adb_entry.is_file(), str(adb_entry)))

    ok = True
    for name, passed, detail in checks:
        status = "OK" if passed else "MISSING"
        if not passed:
            ok = False
        print(f"[{status}] {name}: {detail}")

    cfg = _load_config()
    budget = StepBudget.from_config(cfg)
    print(f"循环: perceive-think-act")
    print(f"单步预算: {budget.step_budget_ms}ms（步后验收: {budget.post_act_mode}）")
    return 0 if ok else 2


def _iter_case_files() -> list[Path]:
    root = cases_dir()
    if not root.is_dir():
        return []
    return sorted(root.rglob("*.json"))


def _cmd_list() -> int:
    files = _iter_case_files()
    if not files:
        print("cases/ 下暂无用例。参考 cases/nl-login-smoke.json")
        return 0
    print(f"共 {len(files)} 个用例：\n")
    for path in files:
        rel = path.relative_to(cases_dir())
        try:
            data = load_case(path)
        except (OSError, json.JSONDecodeError, ValueError):
            print(f"- {rel}")
            continue
        flow = data.get("flow") if isinstance(data.get("flow"), list) else []
        print(f"- {data.get('id', rel)} · {data.get('title', '')}（{len(flow)} 步）")
    return 0


def _optional_case(case_ref: str | None) -> dict:
    if not case_ref:
        return {}
    path = resolve_case_path(case_ref)
    return load_case(path)


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        case_path = resolve_case_path(args.case)
    except (ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    report = run_case(
        case_path,
        config=_load_config(),
        dry_run=args.dry_run,
        max_steps=args.max_steps,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("status") == "failed":
        return 3
    return 0


def _cmd_cycle(args: argparse.Namespace) -> int:
    cfg = _load_config()
    budget = StepBudget.from_config(cfg)
    case = _optional_case(args.case)
    kb_hints: list[str] = []
    for mod in case_modules(case):
        kb_hints.extend(load_kb_hints(mod, config=cfg))
    try:
        result = run_step_cycle(
            nl_step=args.step,
            case=case,
            kb_hints=kb_hints,
            budget=budget,
            with_image=args.image,
        )
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        print(f"执行失败: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    act = result.get("act") if isinstance(result.get("act"), dict) else {}
    return 0 if act.get("ok") else 3


def _cmd_perceive(args: argparse.Namespace) -> int:
    cfg = _load_config()
    budget = StepBudget.from_config(cfg)

    try:
        screen = perceive_for_step(budget=budget, with_image=args.image)
    except (RuntimeError, ValueError) as exc:
        print(f"识别失败: {exc}", file=sys.stderr)
        return 1
    out = {
        "summary": screen_summary(screen),
        "activity": screen.get("activity"),
        "ui": screen.get("ui"),
        "screen": screen.get("screen"),
        "uiHash": screen.get("uiHash"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    load_local_env()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return _cmd_doctor()
    if args.command == "list":
        return _cmd_list()
    if args.command == "run":
        return _cmd_run(args)
    if args.command == "cycle":
        return _cmd_cycle(args)
    if args.command == "perceive":
        return _cmd_perceive(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
