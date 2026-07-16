#!/usr/bin/env python3
"""启动 Web Agent 服务并在浏览器打开。"""

from __future__ import annotations

import argparse
import subprocess
import sys
import webbrowser
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEB_AGENT_DIR.parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="打开 Yaahlan Web Agent")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    cmd = [sys.executable, str(WEB_AGENT_DIR / "server.py"), "--ensure"]
    if args.host:
        cmd.extend(["--host", args.host])
    if args.port is not None:
        cmd.extend(["--port", str(args.port)])

    result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
        return result.returncode

    url = (result.stdout or "").strip().splitlines()[-1]
    print(url)
    if not args.no_open and url.startswith("http"):
        webbrowser.open(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
