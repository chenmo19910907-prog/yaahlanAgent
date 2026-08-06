#!/usr/bin/env python3
"""根据 config/registry.json 生成 MOA-generative/使用方法.md。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import defaultdict
from typing import Any

_MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_MODULE_DIR)
_SCRIPTS = os.path.join(_MODULE_DIR, "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from project_api import generative_root  # noqa: E402

_REGISTRY = str(generative_root() / "config" / "registry.json")
_USAGE = str(generative_root() / "使用方法.md")


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
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
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
        cat_anchor = f"moa-gen-cat-{idx}"
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
    lines.append("## 已录入 MOA-generative 清单（自动生成）")
    lines.append("")
    lines.append(
        "> 本文件由 `MOA-generative/scripts/generate_index.py` 根据 "
        "`MOA-generative/config/registry.json` 自动生成，请勿手动编辑。"
    )
    lines.append("")
    sorted_cats = sorted(by_cat.keys())
    _render_toc(lines, sorted_cats, by_cat)

    lines.append("### 使用说明")
    lines.append("")
    lines.append("- **用途**：把 Tunnel 抓到的客户端 HTTP body，套成 MSE httpproxy 可调的 MOA payload（双写 `header` + `params`）")
    lines.append("- **环境**：测试环境（alpha / stage 代理）；勿用于线上")
    lines.append("- **前置**：Tunnel 拿到 request body；MSE 调用链拿到真实 **ServiceUrl** + **Method**（禁止仅凭 HTTP 路径瞎猜 ServiceUrl）")
    lines.append(
        "- **套壳铁律**：`header` = body 的 JSON 字符串；`params[0].type=json` 且 `value`/`json` 与 header 同内容。"
        "只写 params 易 System error；body 当 TXT 字符串易 ClassCastException"
    )
    lines.append(
        "- **推荐入口**：工作流 `moa-generative-run`（与 `run_generative_moa.py` 同逻辑）；"
        "报告见 `.tmp/workflow_runs/`"
    )
    lines.append(
        "- **strict**：`0`（默认）代理调通即成功（已签到/已点赞等业务拒绝也算过）；"
        "`1` 要求业务 `success=true` / `ec=200`"
    )
    lines.append(
        "- **对照表**：已验证 HTTP↔MOA 见 `MOA-generative/mappings.md`；"
        "步骤详解见 `MOA-generative/README.md`"
    )
    lines.append(
        "- **结果解读**：`Method not found` 改 method 大小写；"
        "`No address found` 改 ServiceUrl；业务拒绝通常表示代理已通"
    )
    lines.append("")

    for idx, cat in enumerate(sorted_cats, start=1):
        cat_anchor = f"moa-gen-cat-{idx}"
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


def _sync_platform_catalog(repo_root: str) -> None:
    script = os.path.join(repo_root, "platform", "scripts", "after_registry_update.py")
    if os.path.isfile(script):
        subprocess.run([sys.executable, script], cwd=repo_root, check=False)


def main() -> int:
    registry = _read_json(_REGISTRY)
    out_rel = registry.get("generated_index_path")
    if isinstance(out_rel, str) and out_rel.strip():
        out_path = os.path.join(_REPO_ROOT, out_rel)
    else:
        out_path = _USAGE

    content = _render(registry)
    _write_text(out_path, content)
    print(f"generated: {out_path}")
    _sync_platform_catalog(_REPO_ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
