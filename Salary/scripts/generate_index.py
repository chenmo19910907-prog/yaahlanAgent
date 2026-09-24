#!/usr/bin/env python3
"""根据 config/registry.json 生成 Salary/使用方法.md。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import defaultdict
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from salary.paths import registry_path, salary_dir, usage_doc_path


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
    return _require_str(item, "name").replace(" ", "-")


def _render(registry: dict[str, Any]) -> str:
    items = registry.get("items")
    if not isinstance(items, list):
        raise ValueError("items 必须是数组")

    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        if isinstance(item, dict):
            by_cat[_require_str(item, "category")].append(item)

    lines: list[str] = [
        "## 已录入 Salary 算薪自动化清单（自动生成）",
        "",
        "> 本文件由 `Salary/scripts/generate_index.py` 根据 `Salary/config/registry.json` 自动生成，请勿手动编辑。",
        "",
        "### 使用说明",
        "",
        "- **环境**：测试 alpha；依赖 MySQL `anchor_salary_2` + MOA `/service/yaahlan-cms/anchor-salary-moa`",
        "- **配置**：复制 `Salary/.env.example` → `Salary/.env`，填写 `MYSQL_*`；MOA lookup 走内网 Redis",
        "- **安装**：`pip install -r Salary/requirements.txt`（建议在 `Salary/.venv`）",
        "- **流程**：MySQL 造数(表1) → MOA1 快照(表2) → MOA2 算薪(表3/4) → 断言",
        "- **业务文档**：`Salary/docs/yaahlan_salary/算薪业务逻辑.md`",
        "",
    ]

    for idx, cat in enumerate(sorted(by_cat.keys()), start=1):
        lines.append(f"## {idx}) {cat}")
        lines.append("")
        for item in sorted(by_cat[cat], key=lambda x: str(x.get("name", ""))):
            name = _require_str(item, "name")
            desc = _require_str(item, "description")
            prompts = item.get("prompts") if isinstance(item.get("prompts"), list) else []
            cmd = _require_str(item, "command").rstrip()
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


def _sync_platform_catalog(repo_root: str) -> None:
    script = os.path.join(repo_root, "platform", "scripts", "after_registry_update.py")
    if os.path.isfile(script):
        subprocess.run([sys.executable, script], cwd=repo_root, check=False)


def main() -> int:
    registry = _read_json(registry_path())
    out_rel = registry.get("generated_index_path")
    if isinstance(out_rel, str) and out_rel.strip():
        out_path = os.path.join(os.path.dirname(salary_dir()), out_rel)
    else:
        out_path = usage_doc_path()

    content = _render(registry)
    _write_text(out_path, content)
    print(f"generated: {out_path}")
    _sync_platform_catalog(os.path.dirname(salary_dir()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
