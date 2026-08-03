"""MSE 模块路径。"""

from __future__ import annotations

import os


def mse_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_json_path() -> str:
    return os.path.join(mse_dir(), "config.json")


def registry_path() -> str:
    return os.path.join(mse_dir(), "config", "registry.json")


def usage_doc_path() -> str:
    return os.path.join(mse_dir(), "使用方法.md")
