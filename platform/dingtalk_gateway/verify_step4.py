#!/usr/bin/env python3
"""Step 4 说明：Stream echo 需 bot_echo.py 前台运行后在群里 @ 测试。"""

from __future__ import annotations

import sys

from env_loader import ENV_LOCAL, load_env_local, require_env


def main() -> int:
    load_env_local()
    try:
        require_env("DINGTALK_CLIENT_ID")
        require_env("DINGTALK_CLIENT_SECRET")
    except RuntimeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    client_id = require_env("DINGTALK_CLIENT_ID")
    if client_id.startswith("ding") and "xxxx" not in client_id:
        print("[OK] 开放平台凭证格式正常")
    else:
        print("[WARN] DINGTALK_CLIENT_ID 可能仍是占位符，请填开放平台 Client ID（ding 开头）")
        print("[WARN] 若只有 Webhook，请用 verify_webhook.py / ask_and_notify.py")

    print()
    print("下一步（Stream @ 双向）：")
    print("  ./run.sh bot_echo.py")
    print("  群里 @机器人 测试123  →  应回复「收到：测试123」")
    print()
    print("通过后（完整 Agent 链路）：")
    print("  ./run.sh server.py")
    print(f"配置文件：{ENV_LOCAL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
