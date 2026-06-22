#!/usr/bin/env python3
"""本地输入 prompt → Cursor Agent → 结果推到钉钉群（Webhook，无需开放平台）。"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from cursor_runner import run_agent_prompt, truncate_for_dingtalk
from env_loader import load_env_local, require_env
from webhook_notify import send_webhook_text


def main() -> int:
    load_env_local()
    parser = argparse.ArgumentParser(description="Agent 执行并把结果推到钉钉群")
    parser.add_argument("prompt", nargs="+", help="发给 Agent 的内容")
    parser.add_argument("--no-notify", action="store_true", help="只跑 Agent，不推钉钉")
    args = parser.parse_args()
    prompt = " ".join(args.prompt).strip()
    if not prompt:
        print("prompt 不能为空", file=sys.stderr)
        return 2

    try:
        require_env("CURSOR_API_KEY")
        if not args.no_notify:
            require_env("DINGTALK_WEBHOOK_URL")
            require_env("DINGTALK_WEBHOOK_SECRET")
    except RuntimeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print("[INFO] 调用 Cursor Agent…")
    try:
        result = run_agent_prompt(prompt)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {exc}", file=sys.stderr)
        if not args.no_notify:
            try:
                send_webhook_text(
                    f"**执行失败**\n\n- 时间：{datetime.now():%Y-%m-%d %H:%M:%S}\n"
                    f"- 输入：{prompt[:200]}\n- 错误：{exc}"
                )
            except Exception:
                pass
        return 1

    print(result)
    if args.no_notify:
        return 0

    md = (
        f"**Agent 完成**  \n"
        f"- 时间：{datetime.now():%Y-%m-%d %H:%M:%S}  \n"
        f"- 输入：{prompt[:300]}  \n\n"
        f"---\n\n{truncate_for_dingtalk(result)}"
    )
    send_webhook_text(md)
    print("[OK] 已推送到钉钉群")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
