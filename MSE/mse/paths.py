"""MSE 模块路径。"""

from __future__ import annotations

import os


def mse_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_json_path() -> str:
    try:
        import sys
        from pathlib import Path

        platform_dir = Path(__file__).resolve().parents[2] / "platform"
        if str(platform_dir) not in sys.path:
            sys.path.insert(0, str(platform_dir))
        from project.bootstrap import module_path

        return str(module_path("mseConfig", "MSE/config.json"))
    except (ImportError, FileNotFoundError, ValueError, OSError):
        return os.path.join(mse_dir(), "config.json")


def registry_path() -> str:
    return os.path.join(mse_dir(), "config", "registry.json")


def usage_doc_path() -> str:
    return os.path.join(mse_dir(), "使用方法.md")
