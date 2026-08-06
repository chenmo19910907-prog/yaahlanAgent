"""线上环境路径。"""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return online_dir().parent


def online_dir() -> Path:
    return Path(__file__).resolve().parent


def config_path() -> Path:
    try:
        import sys

        platform_dir = online_dir().parent / "platform"
        if str(platform_dir) not in sys.path:
            sys.path.insert(0, str(platform_dir))
        from project.bootstrap import module_path

        return module_path("onlineConfig", "online/config.json")
    except (ImportError, FileNotFoundError, ValueError, OSError):
        return online_dir() / "config.json"


def registry_path() -> Path:
    return online_dir() / "config" / "registry.json"


def usage_doc_path() -> Path:
    return online_dir() / "使用方法.md"


def env_local_path() -> Path:
    return online_dir() / ".env.local"


def template_path(name: str) -> Path:
    return online_dir() / "templates" / name
