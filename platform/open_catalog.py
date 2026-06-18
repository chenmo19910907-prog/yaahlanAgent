#!/usr/bin/env python3
"""刷新并打开工具平台能力目录网页（本地 HTTP + Cursor bridge）。"""

from __future__ import annotations

import subprocess
import sys
import webbrowser
from pathlib import Path

PLATFORM_DIR = Path(__file__).resolve().parent
REPO_ROOT = PLATFORM_DIR.parent
GENERATOR = PLATFORM_DIR / "scripts" / "generate_catalog.py"
SERVER = PLATFORM_DIR / "scripts" / "catalog_server.py"


def main() -> int:
    gen_rc = subprocess.call([sys.executable, str(GENERATOR), "--no-open"], cwd=str(REPO_ROOT))
    if gen_rc != 0:
        return gen_rc

    proc = subprocess.run(
        [sys.executable, str(SERVER), "--ensure"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    url = proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else ""
    if not url:
        url = (PLATFORM_DIR / "catalog.html").as_uri()

    if webbrowser.open(url):
        print(f"opened: {url}")
    else:
        print(f"catalog: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
