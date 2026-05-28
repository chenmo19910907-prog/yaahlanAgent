#!/usr/bin/env python3
import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("registry 必须是 JSON object")
    return data


def _require_str(d: Dict[str, Any], key: str) -> str:
    v = d.get(key)
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{key} 必须是非空字符串")
    return v


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _item_anchor(it: Dict[str, Any]) -> str:
    item_id = it.get("id")
    if isinstance(item_id, str) and item_id.strip():
        return item_id.strip()
    name = it.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip().replace(" ", "-")
    raise ValueError("registry item 缺少可用 id（用于目录锚点）")


def _render_toc(
    lines: List[str],
    sorted_cats: List[str],
    by_cat: Dict[str, List[Dict[str, Any]]],
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


def _render(registry: Dict[str, Any]) -> str:
    items = registry.get("items")
    if not isinstance(items, list):
        raise ValueError("items 必须是数组")

    by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for it in items:
        if not isinstance(it, dict):
            continue
        cat = _require_str(it, "category")
        by_cat[cat].append(it)

    lines: List[str] = []
    lines.append("## 已录入 MOA 清单（自动生成）")
    lines.append("")
    lines.append("> 本文件由 `MOA/generate_moa_index.py` 根据 `MOA/moa_registry.json` 自动生成，请勿手动编辑。")
    lines.append("")
    sorted_cats = sorted(by_cat.keys())
    _render_toc(lines, sorted_cats, by_cat)

    lines.append("### 使用说明")
    lines.append("")
    lines.append("- **提示词**：你对我说的自然语言口令")
    lines.append("- **命令**：对应可执行脚本命令（默认已配置 `MOA/.env.local`）")
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
            cmd = _require_str(it, "command").rstrip() + "\n"

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
            lines.append(cmd.rstrip())
            lines.append("```")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    registry_path = os.path.join(base_dir, "moa_registry.json")
    registry = _read_json(registry_path)
    out_rel = registry.get("generated_index_path") or "MOA/MOA清单.md"
    if not isinstance(out_rel, str):
        raise ValueError("generated_index_path 必须是字符串")
    out_path = os.path.join(os.path.dirname(base_dir), out_rel)

    content = _render(registry)
    _write_text(out_path, content)
    print(f"generated: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

