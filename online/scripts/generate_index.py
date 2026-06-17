#!/usr/bin/env python3
"""根据 online/config/registry.json 生成 online/使用方法.md。"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Any

_ONLINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ONLINE_DIR)

from paths import online_dir, registry_path, usage_doc_path


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
    lines.append("## 已录入线上环境清单（自动生成）")
    lines.append("")
    lines.append(
        "> 本文件由 `online/scripts/generate_index.py` 根据 `online/config/registry.json` 自动生成，请勿手动编辑。"
    )
    lines.append("")
    lines.append("### 目录")
    lines.append("")
    sorted_cats = sorted(by_cat.keys())
    for idx, cat in enumerate(sorted_cats, start=1):
        anchor = f"online-cat-{idx}"
        lines.append(f"- [{idx}) {cat}](#{anchor})")
        for item in sorted(by_cat[cat], key=lambda x: str(x.get("name", ""))):
            lines.append(f"  - [{_require_str(item, 'name')}](#{_item_anchor(item)})")
    lines.append("")
    lines.append("### 使用说明")
    lines.append("")
    lines.append("- **提示词**：用户消息须含关键词「**线上环境**」")
    lines.append("- **命令**：对应 `python3 online/online_execute.py <admin|moa|tunnel> ...`")
    lines.append("- **配置**：`cp online/.env.example online/.env.local`（Admin + MOA + Tunnel 鉴权合一）")
    lines.append("- **禁止**：无「线上环境」时调用本模块；含「线上环境」时禁止测试 `Admin/`、`MOA/`、`Tunnel/`")
    lines.append("- **MOA 区号**：默认 **+966**（中国区号显式 `--phone-area-code 86`）")
    lines.append("- **Tunnel**：`g_env=overseas`")
    lines.append("- **在线判定**：Admin `queryUserDetail` 返回 `onlineStatus === 1` 为在线")
    lines.append("")
    lines.append("### 环境配置")
    lines.append("")
    lines.append("```bash")
    lines.append("cp online/.env.example online/.env.local")
    lines.append("# 填入 ADMIN_ONLINE_*、MOA_ONLINE_*、TUNNEL_ONLINE_*")
    lines.append("```")
    lines.append("")
    lines.append("| 变量前缀 | 用途 | 抓包来源 |")
    lines.append("|----------|------|----------|")
    lines.append("| `ADMIN_ONLINE_*` | yaahlan-admin.wemomo.com | www.yaahlan.fun 后台 |")
    lines.append("| `MOA_ONLINE_*` | MSE httpproxy overseas | mse.wemomo.com |")
    lines.append("| `TUNNEL_ONLINE_*` | tunnel.wemomo.com | tunnel 页面 Cookie |")
    lines.append("")
    lines.append("### 子命令速查")
    lines.append("")
    lines.append("| 子命令 | 底层 | 典型场景 |")
    lines.append("|--------|------|----------|")
    lines.append("| `admin` | Admin `--线上环境` | userId 查详情、在线状态 |")
    lines.append("| `moa` | MOA `--线上环境` | 手机号 → userId（+966） |")
    lines.append("| `tunnel` | Tunnel `--线上环境` | 用户 HTTP 抓包列表 |")
    lines.append("")
    lines.append("### 典型组合")
    lines.append("")
    lines.append("```bash")
    lines.append("# 手机号 → userId → 是否在线")
    lines.append("python3 online/online_execute.py moa --query-user-by-phone 19900001111")
    lines.append("python3 online/online_execute.py admin --query-user-id <userId>")
    lines.append("")
    lines.append("# 查用户最近抓包")
    lines.append("python3 online/online_execute.py tunnel --momoid <userId> --since 3600")
    lines.append("```")
    lines.append("")
    lines.append("### 维护")
    lines.append("")
    lines.append("新增能力：编辑 `online/config/registry.json` 后执行：")
    lines.append("")
    lines.append("```bash")
    lines.append("python3 online/scripts/generate_index.py")
    lines.append("```")
    lines.append("")

    for idx, cat in enumerate(sorted_cats, start=1):
        anchor = f"online-cat-{idx}"
        lines.append(f'<a id="{anchor}"></a>')
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
    registry = _read_json(str(registry_path()))
    out_rel = registry.get("generated_index_path")
    if isinstance(out_rel, str) and out_rel.strip():
        out_path = os.path.join(online_dir().parent, out_rel)
    else:
        out_path = str(usage_doc_path())
    content = _render(registry)
    _write_text(out_path, content)
    print(f"generated: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
