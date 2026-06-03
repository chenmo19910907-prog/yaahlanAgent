"""MOA 目录路径常量。"""

from __future__ import annotations

import os


def moa_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_dir() -> str:
    return os.path.join(moa_dir(), "config")


def thresholds_path() -> str:
    return os.path.join(config_dir(), "thresholds.json")


def registry_path() -> str:
    return os.path.join(config_dir(), "registry.json")


def templates_dir() -> str:
    return os.path.join(moa_dir(), "templates")


def usage_doc_path() -> str:
    return os.path.join(moa_dir(), "使用方法.md")
