"""Admin 配置读取。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CONFIG: dict[str, Any] | None = None


def _config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config.json"


def load_config() -> dict[str, Any]:
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    path = _config_path()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Admin/config.json 必须是 object")
    _CONFIG = data
    return data


def defaults(section: str) -> dict[str, Any]:
    cfg = load_config()
    value = cfg.get(section, {})
    if not isinstance(value, dict):
        raise ValueError(f"Admin/config.json.{section} 必须是 object")
    return value
