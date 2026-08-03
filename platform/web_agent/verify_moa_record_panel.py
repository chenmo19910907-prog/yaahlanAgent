#!/usr/bin/env python3
"""验证 MOA 录制面板 HTML/JS 挂载与四种模式定义。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
CHAT_HTML = WEB_AGENT_DIR / "chat.html"
MOA_PANEL_JS = WEB_AGENT_DIR / "moa_record_panel.js"

REQUIRED_HTML_IDS = [
    "btn-moa-record",
    "moa-record-modal",
    "moa-record-mode-list",
    "moa-record-form",
    "moa-record-form-fields",
    "btn-moa-record-submit",
    "btn-moa-record-close",
]

REQUIRED_MODE_IDS = [
    "screenshot",
    "full_request",
    "tunnel_capture",
    "server_code",
]


def main() -> int:
    html = CHAT_HTML.read_text(encoding="utf-8")
    js = MOA_PANEL_JS.read_text(encoding="utf-8")

    for element_id in REQUIRED_HTML_IDS:
        if f'id="{element_id}"' not in html:
            print(f"FAIL: chat.html 缺少 #{element_id}")
            return 1

    if "moa_record_panel.js" not in html:
        print("FAIL: chat.html 未引入 moa_record_panel.js")
        return 1

    if "initMoaRecordPanel" not in html:
        print("FAIL: chat.html 未初始化 MOA 录制面板")
        return 1

    if "fillInputFromMoaRecord" not in html:
        print("FAIL: chat.html 未实现 MOA 录制填入输入框")
        return 1

    for mode_id in REQUIRED_MODE_IDS:
        if not re.search(rf"id:\s*['\"]{re.escape(mode_id)}['\"]", js):
            print(f"FAIL: moa_record_panel.js 缺少模式 {mode_id}")
            return 1

    if "buildPrompt" not in js:
        print("FAIL: moa_record_panel.js 缺少 buildPrompt")
        return 1

    print("OK: MOA 录制面板挂载与四种模式定义通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
