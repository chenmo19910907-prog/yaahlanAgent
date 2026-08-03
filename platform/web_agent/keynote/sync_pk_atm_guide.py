#!/usr/bin/env python3
"""将 workflow/PK提款机搭建指南.md 同步到 keynote 目录供内网 HTML 加载。"""

from __future__ import annotations

import shutil
import socket
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SOURCE = REPO / "workflow" / "PK提款机搭建指南.md"
TARGET = Path(__file__).resolve().parent / "pk_atm_guide.md"
PORT = 18766
URL_PATH = "/keynote/pk-atm-guide"


def _lan_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "127.0.0.1"


def main() -> int:
    if not SOURCE.is_file():
        print(f"源文件不存在: {SOURCE}", file=sys.stderr)
        return 1
    shutil.copy2(SOURCE, TARGET)
    ip = _lan_ip()
    url = f"http://{ip}:{PORT}{URL_PATH}"
    local = f"http://127.0.0.1:{PORT}{URL_PATH}"
    addr_file = TARGET.parent / "pk_atm_guide_url.txt"
    addr_file.write_text(f"{url}\n{local}\n", encoding="utf-8")
    print(f"同步: {SOURCE.name} → {TARGET.name}")
    print(f"内网: {url}")
    print(f"本机: {local}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
