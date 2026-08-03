"""Risk 目录路径常量。"""

from __future__ import annotations

import os


def risk_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_dir() -> str:
    return os.path.join(risk_dir(), "config")


def registry_path() -> str:
    return os.path.join(config_dir(), "registry.json")


def usage_doc_path() -> str:
    return os.path.join(risk_dir(), "使用方法.md")
