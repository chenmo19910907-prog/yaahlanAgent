#!/usr/bin/env python3
"""将 scenes.json 同步进 preview.html / Web_Agent_Keynote.html 的 kn-data（勿用 .tmp 全量生成器覆盖）。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SCENES_FILE = BASE / "scenes.json"
USAGE_FILE = BASE / "usage_biweekly.json"
HTML_FILES = (BASE / "preview.html", BASE / "Web_Agent_Keynote.html")


def _sync_kn_data(text: str, scenes: list) -> str:
    kn_json = json.dumps(scenes, ensure_ascii=False, separators=(",", ":"))
    pattern = re.compile(
        r'(<script id="kn-data" type="application/json">).*?(</script>)',
        re.DOTALL,
    )
    new_text, n = pattern.subn(r"\1" + kn_json + r"\2", text, count=1)
    if n != 1:
        raise SystemExit(f"kn-data 替换失败 ({n})")
    return new_text


def _sync_usage_biweekly(text: str, usage: dict) -> str:
    usage_json = json.dumps(usage, ensure_ascii=False, separators=(",", ":"))
    pattern = re.compile(r"var USAGE_BIWEEKLY = \{.*?\};", re.DOTALL)
    new_text, n = pattern.subn(f"var USAGE_BIWEEKLY = {usage_json};", text, count=1)
    if n != 1:
        raise SystemExit(f"USAGE_BIWEEKLY 替换失败 ({n})")
    return new_text


def sync() -> None:
    scenes = json.loads(SCENES_FILE.read_text(encoding="utf-8"))
    if not isinstance(scenes, list) or not scenes:
        raise SystemExit("scenes.json 须为非空数组")
    usage = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    if not isinstance(usage, dict) or not usage.get("days"):
        raise SystemExit("usage_biweekly.json 须含 days 数组")
    for path in HTML_FILES:
        if not path.is_file():
            raise SystemExit(f"缺少 {path.name}，请先恢复完整 Keynote HTML")
        text = path.read_text(encoding="utf-8")
        text = _sync_kn_data(text, scenes)
        text = _sync_usage_biweekly(text, usage)
        path.write_text(text, encoding="utf-8")
        print(f"updated {path.name} ({len(scenes)} scenes, {len(usage['days'])} usage days)")


if __name__ == "__main__":
    sync()
