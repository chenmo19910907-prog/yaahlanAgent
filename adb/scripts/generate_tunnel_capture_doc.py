#!/usr/bin/env python3
"""根据 adb/config/tunnel_capture_catalog.json 生成 Tunnel抓包常用验收.md。"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_CATALOG = _REPO / "adb" / "config" / "tunnel_capture_catalog.json"
_OUT = _REPO / "adb" / "录制脚本" / "Tunnel抓包常用验收.md"


def main() -> int:
    data = json.loads(_CATALOG.read_text(encoding="utf-8"))
    items = [x for x in data.get("items", []) if isinstance(x, dict)]
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        by_cat[str(item.get("category") or "其他")].append(item)

    lines = [
        "# Tunnel 抓包常用验收",
        "",
        "> 本文件由 `adb/scripts/generate_tunnel_capture_doc.py` 根据 `adb/config/tunnel_capture_catalog.json` 自动生成。",
        "",
        data.get("description", ""),
        "",
        "## CLI",
        "",
        "```bash",
        "# 列出全部",
        "python3 adb/adb_execute.py tunnel capture list",
        "",
        "# 查看单项",
        "python3 adb/adb_execute.py tunnel capture show gift_send",
        "",
        "# 执行验收（须先完成 trigger 操作）",
        "python3 adb/adb_execute.py tunnel capture run gift_send --momoid <userId>",
        "python3 adb/adb_execute.py tunnel capture run gift_backpack --momoid <userId> --set baseProductId=2005001494 --set num=10",
        "```",
        "",
        "底层索引：`adb/config/tunnel_capture_catalog.json`",
        "",
    ]

    for cat in sorted(by_cat.keys()):
        lines.append(f"## {cat}")
        lines.append("")
        for item in by_cat[cat]:
            iid = item.get("id", "")
            lines.append(f"### `{iid}` · {item.get('name', '')}")
            lines.append("")
            if item.get("trigger"):
                lines.append(f"- **触发**：{item['trigger']}")
            if item.get("keyword"):
                lines.append(f"- **关键字**：`{item['keyword']}`")
            if item.get("urlMarker"):
                lines.append(f"- **URL**：`{item['urlMarker']}`")
            if item.get("successPath"):
                sv = item.get("successValue", "")
                lines.append(f"- **成功**：`{item['successPath']}` = {sv}")
            if item.get("failPath"):
                lines.append(f"- **失败读**：`{item['failPath']}`")
            if item.get("readPaths"):
                lines.append(f"- **读取**：{', '.join('`' + p + '`' for p in item['readPaths'])}")
            if item.get("command"):
                lines.append(f"- **命令**：`{item['command']}`")
            if item.get("waitCommand"):
                lines.append(f"- **等待命令**：`{item['waitCommand']}`")
            notes = item.get("notes") or []
            if notes:
                lines.append("- **备注**：")
                for n in notes:
                    lines.append(f"  - {n}")
            lines.append("")

    lines.extend(
        [
            "## 相关",
            "",
            "- [礼物面板抓包.md](./礼物面板抓包.md)",
            "- [弹窗抓包信号.json](./弹窗抓包信号.json)",
            "- `Tunnel/使用方法.md`",
            "- 技能 `adb-tunnel-verify`",
            "",
        ]
    )

    _OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"generated: {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
