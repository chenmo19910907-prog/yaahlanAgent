"""Web Agent 对内分享的固定访问基址（勿用 127.0.0.1 / cloudflare 答复用户）。"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

_DEFAULT_PUBLIC_BASE = "http://172.18.124.255:18766"
_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


@lru_cache(maxsize=1)
def web_agent_public_base_url() -> str:
    env = (os.environ.get("WEB_AGENT_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if env:
        return env
    if _CONFIG_PATH.is_file():
        try:
            cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            configured = str(cfg.get("publicBaseUrl") or "").strip().rstrip("/")
            if configured:
                return configured
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return _DEFAULT_PUBLIC_BASE


def web_agent_chat_url() -> str:
    return f"{web_agent_public_base_url()}/chat.html"


def web_agent_catalog_manual_url() -> str:
    return f"{web_agent_public_base_url()}/catalog-manual/"
