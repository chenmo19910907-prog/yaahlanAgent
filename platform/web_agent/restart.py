#!/usr/bin/env python3
"""强制重启 Web Agent（杀旧进程 + 拉起 server_watch）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parents[1] / "dingtalk_gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from web_agent_restart import (  # noqa: E402
    DEFERRED_RESTART_SESSION_ENV,
    append_deferred_restart_followup,
    force_restart_web_agent,
)


def main() -> int:
    session_id = (os.environ.get(DEFERRED_RESTART_SESSION_ENV) or "").strip()
    outcome = force_restart_web_agent()
    if session_id:
        append_deferred_restart_followup(session_id, outcome)
    print(outcome.message)
    return 0 if outcome.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
