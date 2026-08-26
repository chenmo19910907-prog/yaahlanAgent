#!/usr/bin/env python3
"""强制重启 Web Agent（杀旧进程 + 拉起 server_watch）。"""

from __future__ import annotations

import sys
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parents[1] / "dingtalk_gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from web_agent_restart import force_restart_web_agent  # noqa: E402


def main() -> int:
    outcome = force_restart_web_agent()
    print(outcome.message)
    return 0 if outcome.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
