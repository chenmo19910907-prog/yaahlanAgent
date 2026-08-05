#!/usr/bin/env python3
"""Web Agent 独立 worker：与 HTTP 服务解耦，服务重启不中断 Agent 执行。"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
PLATFORM_DIR = WEB_AGENT_DIR.parent
GATEWAY_DIR = PLATFORM_DIR / "dingtalk_gateway"

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from web_run_executor import execute_web_run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Web Agent run worker")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return execute_web_run(args.run_id.strip())


if __name__ == "__main__":
    raise SystemExit(main())
