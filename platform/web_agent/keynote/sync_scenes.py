#!/usr/bin/env python3
"""将 scenes.json 同步进 preview.html / Web_Agent_Keynote.html 的 kn-data（勿用 .tmp 全量生成器覆盖）。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SCENES_FILE = BASE / "scenes.json"
HTML_FILES = (BASE / "preview.html", BASE / "Web_Agent_Keynote.html")


def sync() -> None:
    scenes = json.loads(SCENES_FILE.read_text(encoding="utf-8"))
    if not isinstance(scenes, list) or not scenes:
        raise SystemExit("scenes.json 须为非空数组")
    kn_json = json.dumps(scenes, ensure_ascii=False, separators=(",", ":"))
    pattern = re.compile(
        r'(<script id="kn-data" type="application/json">).*?(</script>)',
        re.DOTALL,
    )
    for path in HTML_FILES:
        if not path.is_file():
            raise SystemExit(f"缺少 {path.name}，请先恢复完整 Keynote HTML")
        text = path.read_text(encoding="utf-8")
        new_text, n = pattern.subn(r"\1" + kn_json + r"\2", text, count=1)
        if n != 1:
            raise SystemExit(f"{path.name}: kn-data 替换失败 ({n})")
        path.write_text(new_text, encoding="utf-8")
        print(f"updated {path.name} ({len(scenes)} scenes)")


if __name__ == "__main__":
    sync()
