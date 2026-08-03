"""workflow CLI。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from workflow.paths import WORKFLOWS_DIR
from workflow.record import init_workflow, record_from_file, record_from_stdin
from workflow.runner import list_workflows, load_workflow, run_workflow


def _kebab(name: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            out.append("-")
        out.append(ch.lower())
    return "".join(out)


def _add_run_args(parser: argparse.ArgumentParser, workflow_id: str) -> None:
    try:
        wf = load_workflow(workflow_id)
    except (FileNotFoundError, ValueError):
        return
    params = wf.get("params") or {}
    for key, meta in params.items():
        if not isinstance(meta, dict):
            continue
        flag = "--" + _kebab(key)
        parser.add_argument(
            flag,
            dest=key,
            help=meta.get("prompt") or meta.get("label") or key,
        )


def build_parser(run_workflow_id: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="工作流录制与参数化复用")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="列出已录制工作流")

    show_p = sub.add_parser("show", help="查看工作流定义")
    show_p.add_argument("workflow_id", help="工作流 id")

    run_p = sub.add_parser("run", help="按参数执行工作流")
    run_p.add_argument("workflow_id", help="工作流 id")
    run_p.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="额外参数（覆盖同名 CLI 参数）",
    )
    if run_workflow_id:
        _add_run_args(run_p, run_workflow_id)

    init_p = sub.add_parser("init", help="生成空白工作流模板")
    init_p.add_argument("workflow_id", help="工作流 id（文件名）")
    init_p.add_argument("--name", help="显示名称")
    init_p.add_argument(
        "--no-register",
        action="store_true",
        help="仅写 workflows/*.json，不更新 registry",
    )

    record_p = sub.add_parser("record", help="落库工作流 JSON")
    record_p.add_argument("--file", type=Path, help="工作流 JSON 文件")
    record_p.add_argument(
        "--stdin",
        action="store_true",
        help="从标准输入读取 JSON",
    )
    record_p.add_argument(
        "--no-register",
        action="store_true",
        help="仅写 workflows/*.json，不更新 registry",
    )

    return parser


def _collect_params(args: argparse.Namespace) -> dict[str, str]:
    values: dict[str, str] = {}
    wf = load_workflow(args.workflow_id)
    for key in (wf.get("params") or {}):
        val = getattr(args, key, None)
        if val not in (None, ""):
            values[key] = str(val)
    for item in args.set or []:
        if "=" not in item:
            raise ValueError(f"--set 格式应为 KEY=VALUE: {item}")
        k, v = item.split("=", 1)
        values[k.strip()] = v.strip()
    return values


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("command", nargs="?")
    pre.add_argument("workflow_id", nargs="?")
    pre_args, _ = pre.parse_known_args(argv)

    parser = build_parser(
        run_workflow_id=pre_args.workflow_id if pre_args.command == "run" else None
    )

    args = parser.parse_args(argv)

    if args.command == "list":
        for item in list_workflows():
            print(f"{item['id']}\t{item['name']}")
            if item["description"]:
                print(f"  {item['description']}")
        return 0

    if args.command == "show":
        path = WORKFLOWS_DIR / f"{args.workflow_id}.json"
        with path.open("r", encoding="utf-8") as f:
            print(f.read())
        return 0

    if args.command == "run":
        summary = run_workflow(args.workflow_id, _collect_params(args))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if args.command == "init":
        path = init_workflow(
            args.workflow_id,
            name=args.name,
            register=not args.no_register,
        )
        print(f"已生成模板: {path}")
        return 0

    if args.command == "record":
        register = not args.no_register
        if args.stdin:
            path = record_from_stdin(register=register)
        elif args.file:
            path = record_from_file(args.file, register=register)
        else:
            parser.error("record 需要 --file 或 --stdin")
        print(f"已录制工作流: {path}")
        return 0

    parser.error(f"未知命令: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
