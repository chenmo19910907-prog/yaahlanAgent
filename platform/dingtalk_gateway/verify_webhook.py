#!/usr/bin/env python3
"""验收 Webhook 机器人能否推消息到群。"""

from __future__ import annotations

import sys
from datetime import datetime

from env_loader import load_env_local, require_env
from webhook_notify import send_webhook_text


def main() -> int:
    load_env_local()
    try:
        require_env("DINGTALK_WEBHOOK_URL")
        require_env("DINGTALK_WEBHOOK_SECRET")
    except RuntimeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    text = f"**Webhook 验收**  \n时间：{datetime.now():%Y-%m-%d %H:%M:%S}  \n若看到本条，推送通道正常。"
    try:
        send_webhook_text(text, title="Yaahlan 验收")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print("[OK] Webhook 验收通过，请到钉钉群确认消息")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
