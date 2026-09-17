"""MSE configValue JSON 补丁（--set key=value）。"""

from __future__ import annotations

import json
import re
from typing import Any

_SET_RE = re.compile(r"^([^=]+)=(.+)$")


def parse_scalar(raw: str) -> Any:
    text = raw.strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def apply_set_args(config: dict[str, Any], set_args: list[str]) -> tuple[dict[str, Any], list[str]]:
    updated = dict(config)
    changes: list[str] = []
    for item in set_args:
        match = _SET_RE.match(item.strip())
        if not match:
            raise ValueError(f"--set 格式错误，应为 key=value：{item!r}")
        key, raw_value = match.group(1).strip(), match.group(2)
        if not key:
            raise ValueError(f"--set 缺少 key：{item!r}")
        new_value = parse_scalar(raw_value)
        old_value = updated.get(key, "<未设置>")
        updated[key] = new_value
        changes.append(
            f"{key}: {json.dumps(old_value, ensure_ascii=False)} → {json.dumps(new_value, ensure_ascii=False)}"
        )
    return updated, changes


def parse_config_value(raw: Any) -> Any:
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return raw
    return raw
