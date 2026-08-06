"""线上环境 Tunnel 配置（g_env=overseas，与测试 alpha 隔离）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_ONLINE_CONFIG: dict[str, Any] | None = None


def online_config_path() -> Path:
    try:
        import sys

        platform_dir = Path(__file__).resolve().parents[2] / "platform"
        if str(platform_dir) not in sys.path:
            sys.path.insert(0, str(platform_dir))
        from project.bootstrap import module_path

        return module_path("onlineConfig", "online/config.json")
    except (ImportError, FileNotFoundError, ValueError, OSError):
        return Path(__file__).resolve().parents[2] / "online" / "config.json"


def load_online_config() -> dict[str, Any]:
    global _ONLINE_CONFIG
    if _ONLINE_CONFIG is not None:
        return _ONLINE_CONFIG
    path = online_config_path()
    if not path.is_file():
        raise ValueError(f"缺少线上配置: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("online/config.json 必须是 object")
    section = data.get("tunnel", {})
    if not isinstance(section, dict):
        raise ValueError("online/config.json.tunnel 必须是 object")
    _ONLINE_CONFIG = section
    return section


def online_defaults() -> dict[str, Any]:
    cfg = load_online_config()
    value = cfg.get("defaults", {})
    if not isinstance(value, dict):
        raise ValueError("online/config.json.tunnel.defaults 必须是 object")
    return value
