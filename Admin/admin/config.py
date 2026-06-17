"""Admin 配置读取。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CONFIG: dict[str, Any] | None = None
_ONLINE_CONFIG: dict[str, Any] | None = None


def _config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config.json"


def _online_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "online" / "config.json"


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


def load_online_config() -> dict[str, Any]:
    global _ONLINE_CONFIG
    if _ONLINE_CONFIG is not None:
        return _ONLINE_CONFIG
    path = _online_config_path()
    if not path.is_file():
        raise ValueError(f"缺少线上配置: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("online/config.json 必须是 object")
    section = data.get("admin", {})
    if not isinstance(section, dict):
        raise ValueError("online/config.json.admin 必须是 object")
    _ONLINE_CONFIG = section
    return section


def defaults(section: str, *, online: bool = False) -> dict[str, Any]:
    cfg = load_online_config() if online else load_config()
    value = cfg.get(section, {})
    if not isinstance(value, dict):
        label = "online/config.json.admin" if online else "config.json"
        raise ValueError(f"Admin/{label}.{section} 必须是 object")
    return value
