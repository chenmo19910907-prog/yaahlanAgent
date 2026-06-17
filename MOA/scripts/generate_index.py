#!/usr/bin/env python3
"""根据 config/registry.json 生成 MOA/使用方法.md。"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moa.paths import moa_dir, registry_path, usage_doc_path


def _read_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("registry 必须是 JSON object")
    return data


def _require_str(d: dict[str, Any], key: str) -> str:
    v = d.get(key)
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{key} 必须是非空字符串")
    return v


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _item_anchor(it: dict[str, Any]) -> str:
    item_id = it.get("id")
    if isinstance(item_id, str) and item_id.strip():
        return item_id.strip()
    name = it.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip().replace(" ", "-")
    raise ValueError("registry item 缺少可用 id")


def _render_toc(
    lines: list[str],
    sorted_cats: list[str],
    by_cat: dict[str, list[dict[str, Any]]],
) -> None:
    lines.append("### 目录")
    lines.append("")
    for idx, cat in enumerate(sorted_cats, start=1):
        cat_anchor = f"moa-cat-{idx}"
        lines.append(f"- [{idx}) {cat}](#{cat_anchor})")
        for it in sorted(by_cat[cat], key=lambda x: str(x.get("name", ""))):
            name = _require_str(it, "name")
            anchor = _item_anchor(it)
            lines.append(f"  - [{name}](#{anchor})")
    lines.append("")


def _render(registry: dict[str, Any]) -> str:
    items = registry.get("items")
    if not isinstance(items, list):
        raise ValueError("items 必须是数组")

    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for it in items:
        if not isinstance(it, dict):
            continue
        by_cat[_require_str(it, "category")].append(it)

    lines: list[str] = []
    lines.append("## 已录入 MOA 清单（自动生成）")
    lines.append("")
    lines.append("> 本文件由 `MOA/scripts/generate_index.py` 根据 `MOA/config/registry.json` 自动生成，请勿手动编辑。")
    lines.append("")
    sorted_cats = sorted(by_cat.keys())
    _render_toc(lines, sorted_cats, by_cat)

    lines.append("### 使用说明")
    lines.append("")
    lines.append("- **提示词**：你对我说的自然语言口令")
    lines.append("- **命令**：对应可执行脚本命令（默认已配置 `MOA/.env.local`）")
    lines.append("- **线上环境**：见 `online/` 模块（`python3 online/online_execute.py moa ...`）")
    lines.append("- **等级升级经验模式**：`--level-exp-mode min`（默认，该等级最低阈值）或 `max`（该等级最高经验，下一级阈值-1）")
    lines.append("- **定制装扮前置 VIP**：定制头像框 **VIP6**、定制座驾 **VIP8**；升级后用 Admin 重置上传冷却")
    lines.append("")

    for idx, cat in enumerate(sorted_cats, start=1):
        cat_anchor = f"moa-cat-{idx}"
        lines.append(f'<a id="{cat_anchor}"></a>')
        lines.append("")
        lines.append(f"## {idx}) {cat}")
        lines.append("")
        for it in sorted(by_cat[cat], key=lambda x: str(x.get("name", ""))):
            name = _require_str(it, "name")
            desc = _require_str(it, "description")
            prompts = it.get("prompts") if isinstance(it.get("prompts"), list) else []
            cmd = _require_str(it, "command").rstrip()

            lines.append(f'<a id="{_item_anchor(it)}"></a>')
            lines.append("")
            lines.append(f"### {name}")
            lines.append("")
            lines.append(f"- **功能**：{desc}")
            if prompts:
                lines.append("- **提示词**：")
                for p in prompts:
                    if isinstance(p, str) and p.strip():
                        lines.append(f"  - `{p.strip()}`")
            lines.append("- **命令**：")
            lines.append("")
            lines.append("```bash")
            lines.append(cmd)
            lines.append("```")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    registry = _read_json(registry_path())
    out_rel = registry.get("generated_index_path")
    if isinstance(out_rel, str) and out_rel.strip():
        repo_root = os.path.dirname(moa_dir())
        out_path = os.path.join(repo_root, out_rel)
    else:
        out_path = usage_doc_path()

    content = _render(registry)
    _write_text(out_path, content)
    print(f"generated: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
