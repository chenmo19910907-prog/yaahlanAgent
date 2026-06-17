"""线上环境路径。"""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return online_dir().parent


def online_dir() -> Path:
    return Path(__file__).resolve().parent


def config_path() -> Path:
    return online_dir() / "config.json"


def registry_path() -> Path:
    return online_dir() / "config" / "registry.json"


def usage_doc_path() -> Path:
    return online_dir() / "使用方法.md"


def env_local_path() -> Path:
    return online_dir() / ".env.local"


def template_path(name: str) -> Path:
    return online_dir() / "templates" / name
