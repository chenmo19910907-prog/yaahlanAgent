#!/usr/bin/env python3
"""向现有全部 Web Agent 管理员钉钉私聊发送退出提示。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from web_admin_notify import broadcast_quit_admin_hint, list_notifiable_admin_staff_ids  # noqa: E402


def main() -> int:
    targets = list_notifiable_admin_staff_ids()
    if not targets:
        print(json.dumps({"error": "无可通知的管理员"}, ensure_ascii=False))
        return 1
    result = broadcast_quit_admin_hint()
    print(
        json.dumps(
            {
                "total": result["total"],
                "sentCount": len(result["sent"]),
                "failedCount": len(result["failed"]),
                "sent": result["sent"],
                "failed": result["failed"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not result["failed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
