"""MSE 配置输出格式化。"""

from __future__ import annotations

import json
from typing import Any


def format_config_list(
    items: list[dict[str, Any]],
    *,
    limit: int = 20,
    name_space: str = "",
    display_namespace: str = "",
    app_key: str = "",
) -> str:
    total = len(items)
    shown = items[: max(1, limit)] if limit > 0 else items
    ns_label = (display_namespace or name_space or "").strip()
    lines = [
        f"共 {total} 条配置"
        + (f"（namespace={ns_label}）" if ns_label else "")
        + (f"，appKey={app_key}" if app_key else ""),
        "",
        "| configKey | 说明 | 状态 | 修改时间 |",
        "| --- | --- | --- | --- |",
    ]
    for item in shown:
        key = str(item.get("configKey") or "-")
        desc = str(item.get("configDesc") or "-").replace("|", "\\|")
        if len(desc) > 40:
            desc = desc[:40] + "…"
        status = str(item.get("status") or "-")
        modified = str(item.get("modified") or "-")[:19]
        lines.append(f"| {key} | {desc} | {status} | {modified} |")
    if total > len(shown):
        lines.append("")
        lines.append(f"… 还有 {total - len(shown)} 条，可用 --limit 或 --config-key 查看单条。")
    return "\n".join(lines)


def format_config_detail(item: dict[str, Any]) -> str:
    key = str(item.get("configKey") or "-")
    desc = str(item.get("configDesc") or "-")
    value = item.get("configValue")
    value_text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    lines = [
        f"**{key}**",
        f"- 说明：{desc}",
        f"- 状态：{item.get('status') or '-'}",
        f"- namespace：{item.get('nameSpace') or 'Application（私有）'}",
        f"- 修改：{item.get('modified') or '-'}",
        "",
        "```json",
        value_text.strip(),
        "```",
    ]
    return "\n".join(lines)
