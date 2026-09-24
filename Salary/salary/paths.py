"""Salary 模块路径常量。"""

from __future__ import annotations

import os


def salary_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def repo_root() -> str:
    return os.path.dirname(salary_dir())


def registry_path() -> str:
    return os.path.join(salary_dir(), "config", "registry.json")


def usage_doc_path() -> str:
    return os.path.join(salary_dir(), "使用方法.md")
