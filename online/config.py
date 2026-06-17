"""线上环境统一配置（Admin / MOA / Tunnel）。"""

from __future__ import annotations

import json
from typing import Any

from paths import config_path

_ROOT_CONFIG: dict[str, Any] | None = None


def load_root_config() -> dict[str, Any]:
    global _ROOT_CONFIG
    if _ROOT_CONFIG is not None:
        return _ROOT_CONFIG
    path = config_path()
    if not path.is_file():
        raise ValueError(f"缺少线上配置: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("online/config.json 必须是 object")
    _ROOT_CONFIG = data
    return data


def section(name: str) -> dict[str, Any]:
    cfg = load_root_config()
    value = cfg.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"online/config.json.{name} 必须是 object")
    return value


def admin_section() -> dict[str, Any]:
    return section("admin")


def moa_section() -> dict[str, Any]:
    return section("moa")


def tunnel_section() -> dict[str, Any]:
    return section("tunnel")
