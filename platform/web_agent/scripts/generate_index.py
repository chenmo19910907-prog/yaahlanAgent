#!/usr/bin/env python3
"""根据 platform/web_agent/config/registry.json 生成 使用方法.md。"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_WEB_AGENT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _WEB_AGENT.parent.parent


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_str(d: dict[str, Any], key: str) -> str:
    value = d.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} 必须是非空字符串")
    return value


def _item_anchor(item: dict[str, Any]) -> str:
    item_id = item.get("id")
    if isinstance(item_id, str) and item_id.strip():
        return item_id.strip()
    raise ValueError("registry item 缺少 id")


def _render(registry: dict[str, Any]) -> str:
    registry_items = registry.get("items")
    if not isinstance(registry_items, list):
        raise ValueError("items 必须是数组")

    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in registry_items:
        if isinstance(item, dict):
            by_cat[_require_str(item, "category")].append(item)

    lines: list[str] = [
        "## Web Agent 能力清单（自动生成）",
        "",
        "> 由 `platform/web_agent/scripts/generate_index.py` 根据 "
        "`platform/web_agent/config/registry.json` 生成，请勿手动编辑。",
        "",
        "浏览器入口：http://127.0.0.1:18766/chat.html",
        "",
    ]

    for category in sorted(by_cat.keys()):
        lines.append(f"### {category}")
        lines.append("")
        for item in by_cat[category]:
            anchor = _item_anchor(item)
            name = _require_str(item, "name")
            desc = str(item.get("description") or "").strip()
            cmd = str(item.get("command") or "").strip()
            prompts = item.get("prompts") if isinstance(item.get("prompts"), list) else []
            lines.append(f"#### {name} {{#{anchor}}}")
            lines.append("")
            if desc:
                lines.append(desc)
                lines.append("")
            if prompts:
                lines.append("- **提示语示例**：")
                for prompt in prompts:
                    if isinstance(prompt, str) and prompt.strip():
                        lines.append(f"  - {prompt.strip()}")
                lines.append("")
            if cmd:
                lines.append("- **命令**：")
                lines.append("")
                lines.append("```bash")
                lines.append(cmd)
                lines.append("```")
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _sync_platform_catalog() -> None:
    script = _REPO_ROOT / "platform" / "scripts" / "after_registry_update.py"
    if script.is_file():
        subprocess.run([sys.executable, str(script)], cwd=str(_REPO_ROOT), check=False)


def main() -> int:
    registry_path = _WEB_AGENT / "config" / "registry.json"
    registry = _read_json(registry_path)
    out_rel = registry.get("generated_index_path")
    out_path = (
        _REPO_ROOT / out_rel
        if isinstance(out_rel, str) and out_rel.strip()
        else _WEB_AGENT / "使用方法.md"
    )
    out_path.write_text(_render(registry), encoding="utf-8")
    print(f"generated: {out_path}")
    _sync_platform_catalog()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
