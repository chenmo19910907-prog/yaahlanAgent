#!/usr/bin/env python3
"""根据 e2e/config/registry.json 生成 e2e/使用方法.md。"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Any

_E2E_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _E2E_DIR)

from e2e.paths import e2e_dir, registry_path, usage_doc_path


def _read_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("registry 必须是 JSON object")
    return data


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} 必须是非空字符串")
    return value


def _render(registry: dict[str, Any]) -> str:
    items = registry.get("items")
    if not isinstance(items, list):
        raise ValueError("items 必须是数组")

    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        if isinstance(item, dict):
            by_cat[_require_str(item, "category")].append(item)

    lines: list[str] = [
        "## E2E 能力清单（自动生成）",
        "",
        "> 由 `e2e/scripts/generate_index.py` 根据 `e2e/config/registry.json` 生成。",
        "",
        "### 使用说明",
        "",
        "- **定位**：独立于 `adb/`；**识别 → 思考 → 执行** 三步循环",
        "- **入口**：`python3 e2e/e2e_execute.py`",
        "- **识别**：`perceive` · **单步**：`cycle --step`",
        "- **用例**：`cases/*.json` 的 `flow[]`",
        "- **知识库**：`testcase-kb/`、`verified-kb/`",
        "- **报告**：`e2e/reports/`",
        "",
    ]

    for idx, cat in enumerate(sorted(by_cat.keys()), start=1):
        lines.append(f"## {idx}) {cat}")
        lines.append("")
        for item in sorted(by_cat[cat], key=lambda x: str(x.get("name", ""))):
            name = _require_str(item, "name")
            desc = _require_str(item, "description")
            cmd = _require_str(item, "command").rstrip()
            lines.append(f"### {name}")
            lines.append("")
            lines.append(f"- **功能**：{desc}")
            lines.append("- **命令**：")
            lines.append("")
            lines.append("```bash")
            lines.append(cmd)
            lines.append("```")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    registry = _read_json(str(registry_path()))
    out_rel = registry.get("generated_index_path")
    if isinstance(out_rel, str) and out_rel.strip():
        out_path = os.path.join(e2e_dir().parent, out_rel)
    else:
        out_path = str(usage_doc_path())
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(_render(registry))
    print(f"generated: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
