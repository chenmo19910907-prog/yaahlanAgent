"""简易 JSON 路径读写（params[0].value.date）。"""

from __future__ import annotations

import re
from typing import Any

_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def _tokens(path: str) -> list[str | int]:
    parts: list[str | int] = []
    for name, idx in _TOKEN.findall(path):
        if name:
            parts.append(name)
        else:
            parts.append(int(idx))
    if not parts:
        raise ValueError(f"无效 JSON 路径: {path}")
    return parts


def set_path(root: Any, path: str, value: Any) -> None:
    parts = _tokens(path)
    cur = root
    for part in parts[:-1]:
        cur = cur[part]
    cur[parts[-1]] = value
