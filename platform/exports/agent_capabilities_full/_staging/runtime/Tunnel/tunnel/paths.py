"""Tunnel 目录路径。"""

from __future__ import annotations

import os


def tunnel_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def registry_path() -> str:
    return os.path.join(tunnel_dir(), "config", "registry.json")


def usage_doc_path() -> str:
    return os.path.join(tunnel_dir(), "使用方法.md")
