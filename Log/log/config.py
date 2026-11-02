"""Kibana Discover 默认配置。"""

from __future__ import annotations

import json
import os
from typing import Any

from .paths import config_json_path


def load_defaults() -> dict[str, Any]:
    path = config_json_path()
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def kibana_base_url() -> str:
    cfg = load_defaults()
    raw = os.environ.get("KIBANA_BASE_URL") or cfg.get("kibanaBaseUrl") or ""
    return str(raw).rstrip("/")


def kibana_bsearch_path() -> str:
    cfg = load_defaults()
    return str(os.environ.get("KIBANA_BSEARCH_PATH") or cfg.get("bsearchPath") or "/alpha-public/internal/bsearch")


def kibana_index() -> str:
    cfg = load_defaults()
    return str(os.environ.get("KIBANA_INDEX") or cfg.get("defaultIndex") or "yaahlan-log*")


def kibana_version() -> str:
    cfg = load_defaults()
    return str(os.environ.get("KIBANA_VERSION") or cfg.get("kbnVersion") or "7.17.29")
