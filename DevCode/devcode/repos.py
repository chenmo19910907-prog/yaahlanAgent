"""DevCode 开发仓清单与 clone URL 解析。"""

from __future__ import annotations

import json
from typing import Any

from devcode.paths import repos_config_path


def _load_repos_config() -> dict[str, Any]:
    with open(repos_config_path(), "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("repos.json 必须是 object")
    return data


def repo_names() -> list[str]:
    cfg = _load_repos_config()
    names = cfg.get("repos")
    if not isinstance(names, list):
        raise ValueError("repos.json repos 必须是数组")
    return [str(x).strip() for x in names if isinstance(x, str) and str(x).strip()]


def default_clone_base() -> str:
    cfg = _load_repos_config()
    base = cfg.get("default_clone_base")
    if isinstance(base, str) and base.strip():
        return base.strip().rstrip("/")
    return "https://git.wemomo.com/voga"


def clone_url(name: str) -> str:
    name = name.strip()
    cfg = _load_repos_config()
    overrides = cfg.get("clone_urls")
    if isinstance(overrides, dict):
        raw = overrides.get(name)
        if isinstance(raw, str) and raw.strip():
            url = raw.strip().rstrip("/")
            return url if url.endswith(".git") else f"{url}.git"
    return f"{default_clone_base()}/{name}.git"
