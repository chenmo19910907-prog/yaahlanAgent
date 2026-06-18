"""E2E 模块路径。"""

from __future__ import annotations

from pathlib import Path


def e2e_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def repo_root() -> Path:
    return e2e_dir().parent


def config_path() -> Path:
    return e2e_dir() / "config.json"


def registry_path() -> Path:
    return e2e_dir() / "config" / "registry.json"


def cases_dir() -> Path:
    return e2e_dir() / "cases"


def reports_dir() -> Path:
    return e2e_dir() / "reports"


def usage_doc_path() -> Path:
    return e2e_dir() / "使用方法.md"
