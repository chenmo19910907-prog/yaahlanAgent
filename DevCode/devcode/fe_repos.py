"""yaahlan-fe 组下独立 H5 仓的 clone URL（与 repos.json 九仓清单分离）。"""

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


def fe_clone_transport() -> str:
    cfg = _load_repos_config()
    raw = cfg.get("fe_clone_transport")
    if isinstance(raw, str) and raw.strip().lower() in ("ssh", "https"):
        return raw.strip().lower()
    return "ssh"


def fe_clone_url(repo_name: str) -> str:
    """返回独立前端仓 git clone URL（默认 SSH，避免无交互 HTTPS 失败）。"""
    name = (repo_name or "").strip().removesuffix(".git")
    if not name:
        raise ValueError("仓库名不能为空")
    cfg = _load_repos_config()
    if fe_clone_transport() == "ssh":
        base = cfg.get("fe_clone_base_ssh")
        if not isinstance(base, str) or not base.strip():
            base = "git@git.wemomo.com:yaahlan-fe"
        base = base.strip().rstrip("/")
        return f"{base}/{name}.git"
    base = cfg.get("fe_clone_base_https")
    if not isinstance(base, str) or not base.strip():
        base = "https://git.wemomo.com/yaahlan-fe"
    base = base.strip().rstrip("/")
    return f"{base}/{name}.git"
