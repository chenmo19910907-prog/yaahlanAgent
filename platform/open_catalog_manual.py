#!/usr/bin/env python3
"""生成并打开工具台能力使用说明书网页。"""

from __future__ import annotations

import subprocess
import sys
import webbrowser
from pathlib import Path

PLATFORM_DIR = Path(__file__).resolve().parent
REPO_ROOT = PLATFORM_DIR.parent
GENERATOR = PLATFORM_DIR / "scripts" / "generate_catalog_manual_html.py"
OUTPUT_HTML = PLATFORM_DIR / "exports" / "catalog-manual" / "index.html"
WEB_AGENT_PORT = 18766


def main() -> int:
    rc = subprocess.call([sys.executable, str(GENERATOR)], cwd=str(REPO_ROOT))
    if rc != 0:
        return rc
    url = f"http://127.0.0.1:{WEB_AGENT_PORT}/catalog-manual/"
    if webbrowser.open(url):
        print(f"opened: {url}")
    else:
        print(f"manual: {OUTPUT_HTML.as_uri()}")
        print(f"web (需 Web Agent): {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
