"""线上环境 MOA 配置（与测试 alpha/stage 隔离）。"""

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
    section = data.get("moa", {})
    if not isinstance(section, dict):
        raise ValueError("online/config.json.moa 必须是 object")
    _ONLINE_CONFIG = section
    return section


def online_defaults() -> dict[str, Any]:
    cfg = load_online_config()
    value = cfg.get("defaults", {})
    if not isinstance(value, dict):
        raise ValueError("online/config.json.moa.defaults 必须是 object")
    return value


def online_query_login_status() -> dict[str, Any]:
    cfg = load_online_config()
    value = cfg.get("query_login_status", {})
    if not isinstance(value, dict):
        raise ValueError("online/config.json.moa.query_login_status 必须是 object")
    return value


def online_service_url_map() -> dict[str, str]:
    cfg = load_online_config()
    raw = cfg.get("service_url_map", {})
    if not isinstance(raw, dict):
        raise ValueError("online/config.json.moa.service_url_map 必须是 object")
    out: dict[str, str] = {}
    for key, value in raw.items():
        src = str(key).strip()
        dst = str(value).strip()
        if src and dst:
            out[src] = dst
    return out


def remap_online_service_url(url: str) -> str:
    """测试环境 ServiceUrl → 线上 overseas 可路由地址（见 online/config.json）。"""
    src = str(url or "").strip()
    if not src:
        return src
    return online_service_url_map().get(src, src)
