#!/usr/bin/env python3
"""根据 DingTalk/config/registry.json 生成 DingTalk/使用方法.md。"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_DINGTALK = Path(__file__).resolve().parent.parent
_ROOT = _DINGTALK.parent
_CATEGORY_ORDER = ["已登记目录", "钉钉目录", "testcase-kb 同步", "prd-kb 同步"]


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


def _folders_as_items() -> list[dict[str, Any]]:
    """将 folders.json 中的目录登记转为能力清单条目（单一数据源）。"""
    folders_path = _DINGTALK / "config" / "folders.json"
    if not folders_path.is_file():
        return []
    data = _read_json(folders_path)
    folders = data.get("folders")
    if not isinstance(folders, list):
        return []

    items: list[dict[str, Any]] = []
    for folder in folders:
        if not isinstance(folder, dict):
            continue
        fid = str(folder.get("id") or "").strip()
        name = str(folder.get("name") or "").strip()
        url = str(folder.get("folderUrl") or "").strip()
        if not fid or not name or not url:
            continue
        desc = str(folder.get("description") or folder.get("shortName") or "").strip()
        if folder.get("default"):
            desc = f"{desc}（默认目录）" if desc else "默认目录"
        prompts = folder.get("prompts") if isinstance(folder.get("prompts"), list) else []
        aliases = folder.get("aliases") if isinstance(folder.get("aliases"), list) else []
        merged_prompts = [
            p.strip() for p in [*prompts, *aliases] if isinstance(p, str) and p.strip()
        ]
        items.append(
            {
                "id": fid,
                "name": name,
                "category": "已登记目录",
                "description": desc,
                "prompts": merged_prompts,
                "command": (
                    f"python3 DingTalk/lookup_execute.py --list --folder-id {fid}\n"
                    f"python3 DingTalk/lookup_execute.py <关键词> --folder-id {fid}"
                ),
                "_folder_url": url,
                "_folder_id": fid,
                "_folder_default": bool(folder.get("default")),
            }
        )
    return items


def _sorted_categories(by_cat: dict[str, list[dict[str, Any]]]) -> list[str]:
    def _key(cat: str) -> tuple[int, str]:
        try:
            return (_CATEGORY_ORDER.index(cat), cat)
        except ValueError:
            return (len(_CATEGORY_ORDER), cat)

    return sorted(by_cat.keys(), key=_key)


def _render(registry: dict[str, Any]) -> str:
    registry_items = registry.get("items")
    if not isinstance(registry_items, list):
        raise ValueError("items 必须是数组")

    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in [* _folders_as_items(), *registry_items]:
        if isinstance(item, dict):
            by_cat[_require_str(item, "category")].append(item)

    lines: list[str] = []
    lines.append("## 已录入 DingTalk 目录能力清单（自动生成）")
    lines.append("")
    lines.append(
        "> 本文件由 `DingTalk/scripts/generate_index.py` 根据 "
        "`DingTalk/config/registry.json` 与 `DingTalk/config/folders.json` 自动生成，请勿手动编辑。"
    )
    lines.append("")
    sorted_cats = _sorted_categories(by_cat)
    lines.append("### 能力清单")
    lines.append("")
    for idx, cat in enumerate(sorted_cats, start=1):
        cat_anchor = f"dingtalk-cat-{idx}"
        lines.append(f"- [{idx}) {cat}](#{cat_anchor})")
        for item in sorted(by_cat[cat], key=lambda x: str(x.get("name", ""))):
            lines.append(f"  - [{_require_str(item, 'name')}](#{_item_anchor(item)})")
    lines.append("")
    lines.append("### 使用说明")
    lines.append("")
    lines.append("- **提示词**：自然语言口令")
    lines.append("- **命令**：从仓库根目录执行")
    lines.append("- **鉴权**：`DINGTALK_COOKIE`（`.cursor/mcp.json` 或 `~/.dingtalk_doc_cookie`）；读表还需 `dingtalk-excel-read` Aegis")
    default_id = registry.get("default_folder_id")
    if isinstance(default_id, str) and default_id.strip():
        lines.append(f"- **默认目录**：`{default_id.strip()}`（见能力清单 → 已登记目录）")
    else:
        lines.append("- **默认目录**：`DingTalk/config/kb.json` → `folderId` / `folderUrl`")
    lines.append("- **登记配置**：`DingTalk/config/folders.json`")
    lines.append("")

    for idx, cat in enumerate(sorted_cats, start=1):
        lines.append(f'<a id="dingtalk-cat-{idx}"></a>')
        lines.append("")
        lines.append(f"## {idx}) {cat}")
        lines.append("")
        for item in sorted(by_cat[cat], key=lambda x: str(x.get("name", ""))):
            name = _require_str(item, "name")
            desc = _require_str(item, "description")
            prompts = item.get("prompts") if isinstance(item.get("prompts"), list) else []
            cmd = _require_str(item, "command").rstrip()
            lines.append(f'<a id="{_item_anchor(item)}"></a>')
            lines.append("")
            lines.append(f"### {name}")
            lines.append("")
            lines.append(f"- **功能**：{desc}")
            folder_url = item.get("_folder_url")
            folder_id = item.get("_folder_id")
            if isinstance(folder_url, str) and folder_url.strip():
                lines.append(f"- **目录链接**：[{folder_url.strip()}]({folder_url.strip()})")
            if isinstance(folder_id, str) and folder_id.strip():
                default_mark = "（默认）" if item.get("_folder_default") else ""
                lines.append(f"- **目录 id**：`{folder_id.strip()}`{default_mark}")
            if prompts:
                lines.append("- **提示词**：")
                for prompt in prompts:
                    if isinstance(prompt, str) and prompt.strip():
                        lines.append(f"  - `{prompt.strip()}`")
            lines.append("- **命令**：")
            lines.append("")
            lines.append("```bash")
            lines.append(cmd)
            lines.append("```")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    registry_path = _DINGTALK / "config" / "registry.json"
    registry = _read_json(registry_path)
    out_rel = registry.get("generated_index_path")
    out_path = _ROOT / out_rel if isinstance(out_rel, str) and out_rel.strip() else _DINGTALK / "使用方法.md"
    out_path.write_text(_render(registry), encoding="utf-8")
    print(f"generated: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
