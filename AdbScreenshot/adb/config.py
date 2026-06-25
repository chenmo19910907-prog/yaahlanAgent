"""配置加载。"""

from __future__ import annotations

import json
import os
from typing import Any


def package_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config() -> dict[str, Any]:
    path = os.path.join(package_dir(), "config.json")
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("config.json 必须是 JSON 对象")
    return data


def default_wireless_registry_path() -> str:
    env_path = os.environ.get("ADB_WIRELESS_REGISTRY", "").strip()
    if env_path:
        return os.path.expanduser(env_path)

    registry = load_config().get("wireless_device_registry")
    if isinstance(registry, dict):
        configured = str(registry.get("json_path") or "").strip()
        if configured:
            return os.path.expanduser(configured)

    return os.path.join(package_dir(), "wireless_devices.json")


def default_screenshot_dir() -> str:
    env_path = os.environ.get("ADB_SCREENSHOT_DIR", "").strip()
    if env_path:
        return os.path.expanduser(env_path)

    defaults = load_config().get("defaults")
    if isinstance(defaults, dict):
        configured = str(defaults.get("screenshot_dir") or "").strip()
        if configured:
            return os.path.expanduser(configured)

    return os.path.expanduser("~/Desktop/adb-screenshots")


def adb_binary() -> str:
    return os.environ.get("ADB_BINARY", "adb").strip() or "adb"
