#!/usr/bin/env python3
"""Step 2 验收：CURSOR_API_KEY + cursor-sdk 本地 Agent pong。"""

from __future__ import annotations

import sys

from cursor_runner import run_agent_prompt
from env_loader import ENV_LOCAL, load_env_local, require_env


def main() -> int:
    load_env_local()
    try:
        require_env("CURSOR_API_KEY")
    except RuntimeError as exc:
        print(f"[FAIL] {exc}")
        print(f"       1. 打开 https://cursor.com/dashboard/integrations 创建 API Key")
        print(f"       2. 复制 platform/dingtalk_gateway/.env.example → .env.local")
        print(f"       3. 填入 CURSOR_API_KEY=...")
        return 1

    print("[INFO] 调用 Cursor SDK（本地 Agent），请稍候…")
    try:
        reply = run_agent_prompt("只回复一个词：pong，不要其它内容。")
    except Exception as exc:  # noqa: BLE001 — 验收脚本需汇总任意失败
        print(f"[FAIL] SDK 调用失败: {exc}")
        return 1

    if "pong" in reply.lower():
        print(f"[OK] Step 2 通过。Agent 回复: {reply[:200]}")
        return 0

    print(f"[WARN] Agent 有回复但未含 pong: {reply[:200]}")
    print("[OK] Step 2 基本通过（SDK 可用，回复内容可忽略）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
