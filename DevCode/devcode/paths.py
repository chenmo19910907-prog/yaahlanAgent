"""DevCode 目录路径常量。"""

from __future__ import annotations

import os


def devcode_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def repo_root() -> str:
    return os.path.dirname(devcode_dir())


def config_dir() -> str:
    return os.path.join(devcode_dir(), "config")


def registry_path() -> str:
    return os.path.join(config_dir(), "registry.json")


def repos_config_path() -> str:
    return os.path.join(config_dir(), "repos.json")


def usage_doc_path() -> str:
    return os.path.join(devcode_dir(), "使用方法.md")


def voga_repos_dir() -> str:
    with open(repos_config_path(), "r", encoding="utf-8") as f:
        import json

        data = json.load(f)
    sub = data.get("repos_dir")
    if not isinstance(sub, str) or not sub.strip():
        sub = "voga-repos"
    return os.path.join(repo_root(), sub.strip())
