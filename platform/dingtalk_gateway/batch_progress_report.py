#!/usr/bin/env python3
"""批量操作进度上报 CLI（Agent / 脚本每完成一项调用一次）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from batch_progress import build_batch_progress_message, report_batch_progress
from batch_result import save_batch_result


def main() -> int:
    parser = argparse.ArgumentParser(description="上报钉钉网关批量操作进度")
    parser.add_argument("--user-key", required=True, help="网关 user_key（提示词中给出）")
    parser.add_argument(
        "--current",
        type=int,
        required=True,
        help="已完成的批量项数（如已处理 3 个手机号则填 3；不是项内子步骤序号）",
    )
    parser.add_argument(
        "--total",
        type=int,
        required=True,
        help="批量项总数（如 10 个手机号则填 10）",
    )
    parser.add_argument(
        "--label",
        default="",
        help="批量操作类型，如「发钻石」「查注册」（不是步骤 1/2/3）",
    )
    parser.add_argument(
        "--detail",
        default="",
        help="当前刚完成的批量项标识，如手机号或 userId",
    )
    parser.add_argument(
        "--result-text",
        default="",
        help="批量最终结果 Markdown（任务结束时推送到群里；与 --result-file 二选一）",
    )
    parser.add_argument(
        "--result-file",
        default="",
        help="批量最终结果文件路径（Markdown/文本）",
    )
    args = parser.parse_args()

    try:
        state = report_batch_progress(
            args.user_key,
            current=args.current,
            total=args.total,
            label=args.label,
            detail=args.detail,
        )
    except ValueError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    result_body = (args.result_text or "").strip()
    if args.result_file:
        path = Path(args.result_file)
        if not path.is_file():
            print(f"[FAIL] 结果文件不存在: {path}", file=sys.stderr)
            return 1
        result_body = path.read_text(encoding="utf-8").strip()
    if result_body:
        save_batch_result(args.user_key, result_body)

    print(build_batch_progress_message(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
