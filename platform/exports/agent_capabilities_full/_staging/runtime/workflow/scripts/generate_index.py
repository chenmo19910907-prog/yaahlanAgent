#!/usr/bin/env python3
"""根据 config/registry.json 生成 workflow/使用方法.md。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import defaultdict
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workflow.paths import REGISTRY_PATH, USAGE_DOC_PATH, WORKFLOW_DIR


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


def _item_sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
    order = item.get("order")
    if isinstance(order, int):
        return (0, order, "")
    return (1, 0, str(item.get("name", "")))


def _playbook_anchor(playbook: dict[str, Any]) -> str:
    playbook_id = playbook.get("id")
    if isinstance(playbook_id, str) and playbook_id.strip():
        return playbook_id.strip()
    title = playbook.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip().replace(" ", "-")
    raise ValueError("playbook 缺少可用 id")


def _render_playbook(playbook: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    title = _require_str(playbook, "title")
    summary = _require_str(playbook, "summary")
    lines.append(f'<a id="{_playbook_anchor(playbook)}"></a>')
    lines.append("")
    lines.append(f"### {title}")
    lines.append("")
    lines.append(summary)
    lines.append("")

    defaults = playbook.get("defaults")
    if isinstance(defaults, dict) and defaults:
        lines.append("**默认参数**")
        lines.append("")
        for key, value in defaults.items():
            lines.append(f"- `{key}`：`{value}`")
        lines.append("")

    sheets = playbook.get("sheets")
    if isinstance(sheets, list) and sheets:
        lines.append("**钉钉 Sheet**")
        lines.append("")
        lines.append("| Sheet | 内容 |")
        lines.append("| --- | --- |")
        for row in sheets:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            content = str(row.get("content") or "").strip()
            if name:
                lines.append(f"| {name} | {content} |")
        lines.append("")

    steps = playbook.get("steps")
    if isinstance(steps, list) and steps:
        lines.append("**六步顺序**")
        lines.append("")
        for row in sorted(steps, key=lambda x: int(x.get("order") or 0)):
            if not isinstance(row, dict):
                continue
            order = str(row.get("order") or "")
            workflow_id = str(row.get("workflowId") or "")
            sheet = str(row.get("sheet") or "")
            note = str(row.get("note") or "")
            lines.append(f"#### 第 {order} 步 · `{workflow_id}` → Sheet「{sheet}」")
            lines.append("")
            if note:
                lines.append(note)
                lines.append("")
            operations = row.get("operations")
            if isinstance(operations, list) and operations:
                lines.append("**执行操作（按顺序）**")
                lines.append("")
                for idx, op in enumerate(operations, start=1):
                    if isinstance(op, str) and op.strip():
                        lines.append(f"{idx}. {op.strip()}")
                lines.append("")

    prompts = playbook.get("prompts")
    if isinstance(prompts, list) and prompts:
        lines.append("**提示词**")
        lines.append("")
        for prompt in prompts:
            if isinstance(prompt, str) and prompt.strip():
                lines.append(f"- `{prompt.strip()}`")
        lines.append("")

    notes = playbook.get("notes")
    if isinstance(notes, list) and notes:
        lines.append("**注意**")
        lines.append("")
        for note in notes:
            if isinstance(note, str) and note.strip():
                lines.append(f"- {note.strip()}")
        lines.append("")

    return lines


def _render_toc(
    lines: list[str],
    sorted_cats: list[str],
    by_cat: dict[str, list[dict[str, Any]]],
    playbooks_by_cat: dict[str, list[dict[str, Any]]],
) -> None:
    lines.append("### 目录")
    lines.append("")
    for idx, cat in enumerate(sorted_cats, start=1):
        cat_anchor = f"workflow-cat-{idx}"
        lines.append(f"- [{idx}) {cat}](#{cat_anchor})")
        for playbook in playbooks_by_cat.get(cat, []):
            title = _require_str(playbook, "title")
            anchor = _playbook_anchor(playbook)
            lines.append(f"  - [{title}](#{anchor})")
        for item in sorted(by_cat[cat], key=_item_sort_key):
            name = _require_str(item, "name")
            anchor = _item_anchor(item)
            lines.append(f"  - [{name}](#{anchor})")
    lines.append("")


def _render(registry: dict[str, Any]) -> str:
    items = registry.get("items")
    if not isinstance(items, list):
        raise ValueError("items 必须是数组")

    playbooks_raw = registry.get("playbooks")
    playbooks: list[dict[str, Any]] = [
        pb for pb in (playbooks_raw if isinstance(playbooks_raw, list) else []) if isinstance(pb, dict)
    ]
    playbooks_by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for playbook in playbooks:
        playbooks_by_cat[_require_str(playbook, "category")].append(playbook)

    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        if not isinstance(item, dict):
            continue
        by_cat[_require_str(item, "category")].append(item)

    lines: list[str] = []
    lines.append("## 已录入工作流清单（自动生成）")
    lines.append("")
    lines.append(
        "> 本文件由 `workflow/scripts/generate_index.py` 根据 "
        "`workflow/config/registry.json` 自动生成，请勿手动编辑。"
    )
    lines.append("")
    sorted_cats = sorted(set(by_cat.keys()) | set(playbooks_by_cat.keys()))
    _render_toc(lines, sorted_cats, by_cat, playbooks_by_cat)

    lines.append("### 使用说明")
    lines.append("")
    lines.append("- **录制**：Agent 描述多步流程后写入 `workflow/workflows/<id>.json`，执行 `record` 落库")
    lines.append("- **复用**：`python3 workflow/workflow_execute.py run <id> --参数 ...`")
    lines.append("- **参数**：工作流 JSON 的 `params` 定义占位符，步骤里用 `{{paramName}}` 引用")
    lines.append("- **步骤类型**：`moa_template`（改 MOA 模板字段）、`shell`（执行 shell 命令）")
    lines.append("")

    for idx, cat in enumerate(sorted_cats, start=1):
        cat_anchor = f"workflow-cat-{idx}"
        lines.append(f'<a id="{cat_anchor}"></a>')
        lines.append("")
        lines.append(f"## {idx}) {cat}")
        lines.append("")
        for playbook in playbooks_by_cat.get(cat, []):
            lines.extend(_render_playbook(playbook))
        for item in sorted(by_cat[cat], key=_item_sort_key):
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


def _sync_platform_catalog(repo_root: str) -> None:
    script = os.path.join(repo_root, "platform", "scripts", "after_registry_update.py")
    if os.path.isfile(script):
        subprocess.run([sys.executable, script], cwd=repo_root, check=False)


def main() -> int:
    registry = _read_json(str(REGISTRY_PATH))
    content = _render(registry)
    _write_text(str(USAGE_DOC_PATH), content)
    print(f"generated: {USAGE_DOC_PATH}")
    _sync_platform_catalog(str(WORKFLOW_DIR.parent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
