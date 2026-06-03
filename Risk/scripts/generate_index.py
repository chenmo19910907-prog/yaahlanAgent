#!/usr/bin/env python3
"""根据 config/registry.json 生成 Risk/使用方法.md。"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from risk.paths import registry_path, risk_dir, usage_doc_path


def _read_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("registry 必须是 JSON object")
    return data


def _require_str(d: dict[str, Any], key: str) -> str:
    value = d.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} 必须是非空字符串")
    return value


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _item_anchor(item: dict[str, Any]) -> str:
    item_id = item.get("id")
    if isinstance(item_id, str) and item_id.strip():
        return item_id.strip()
    name = item.get("name")
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
        cat_anchor = f"risk-cat-{idx}"
        lines.append(f"- [{idx}) {cat}](#{cat_anchor})")
        for item in sorted(by_cat[cat], key=lambda x: str(x.get("name", ""))):
            name = _require_str(item, "name")
            anchor = _item_anchor(item)
            lines.append(f"  - [{name}](#{anchor})")
    lines.append("")


def _render(registry: dict[str, Any]) -> str:
    items = registry.get("items")
    if not isinstance(items, list):
        raise ValueError("items 必须是数组")

    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        if not isinstance(item, dict):
            continue
        by_cat[_require_str(item, "category")].append(item)

    lines: list[str] = []
    lines.append("## 已录入 Risk 清单（自动生成）")
    lines.append("")
    lines.append("> 本文件由 `Risk/scripts/generate_index.py` 根据 `Risk/config/registry.json` 自动生成，请勿手动编辑。")
    lines.append("")
    sorted_cats = sorted(by_cat.keys())
    _render_toc(lines, sorted_cats, by_cat)

    lines.append("### 使用说明")
    lines.append("")
    lines.append("- **提示词**：你对我说的自然语言口令")
    lines.append("- **命令**：对应可执行脚本命令（默认已配置 `Risk/.env.local` 或 `Risk/config.json`）")
    lines.append("- **鉴权**：开放接口 `/open/menu/operate` 通常仅需 body 中的 `token`（`SEC_RISK_TOKEN`），一般不需要 Cookie")
    lines.append("- **分批**：设备/手机号/user_id 单次最多 **5** 个 element；超出时脚本默认自动分批（`--strict-limit` 可改为报错）")
    lines.append("- **测试机解除设备风控**：Android/鸿蒙取 **mmuidv3**，iOS 取 **mmuid**；接口 dimension 均为 `mmuid`")
    lines.append("- **调试**：追加 `--dump-body` 可在 stderr 查看最终请求 body")
    lines.append("")

    for idx, cat in enumerate(sorted_cats, start=1):
        cat_anchor = f"risk-cat-{idx}"
        lines.append(f'<a id="{cat_anchor}"></a>')
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
    registry = _read_json(registry_path())
    out_rel = registry.get("generated_index_path")
    if isinstance(out_rel, str) and out_rel.strip():
        repo_root = os.path.dirname(risk_dir())
        out_path = os.path.join(repo_root, out_rel)
    else:
        out_path = usage_doc_path()

    content = _render(registry)
    _write_text(out_path, content)
    print(f"generated: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
