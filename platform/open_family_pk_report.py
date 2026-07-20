#!/usr/bin/env python3
"""生成并打开家族 PK 测试自动化建设成果 Showcase 页。"""

from __future__ import annotations

import subprocess
import sys
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = REPO_ROOT / "platform" / "family_pk_report" / "generate.py"
EXPORTS_DIR = REPO_ROOT / "platform" / "family_pk_report" / "exports"


def main() -> int:
    cmd = [sys.executable, str(GENERATOR), "--scan-tmp", "--hub"]
    rc = subprocess.call(cmd, cwd=str(REPO_ROOT))
    if rc != 0:
        return rc

    hub = EXPORTS_DIR / "index.html"
    url = hub.as_uri() if hub.is_file() else EXPORTS_DIR.as_uri()
    if webbrowser.open(url):
        print(f"opened: {url}")
    else:
        print(f"report hub: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
