"""模块级步骤提示：observe 不可靠时回退到 verified 路径坐标。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import e2e_dir
from .scene_gate import ui_tree_unreliable

# 兼容旧 import
__all__ = [
    "lookup_step_hint",
    "case_modules",
    "ui_tree_unreliable",
]


def _hints_path() -> Path:
    return e2e_dir() / "config" / "step_hints.json"


@lru_cache(maxsize=1)
def _load_all_hints() -> dict[str, dict[str, dict[str, Any]]]:
    path = _hints_path()
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def lookup_step_hint(modules: list[str] | str, nl_step: str) -> dict[str, Any] | None:
    """按用例 modules 顺序查找 verified 路径提示。"""
    if isinstance(modules, str):
        modules = [modules]
    step = (nl_step or "").strip()
    all_hints = _load_all_hints()
    for module in modules:
        module_map = all_hints.get((module or "").strip())
        if not isinstance(module_map, dict):
            continue
        hint = module_map.get(step)
        if isinstance(hint, dict):
            return hint
    return None


def case_modules(case: dict[str, Any] | None) -> list[str]:
    case = case or {}
    modules: list[str] = []
    raw = case.get("modules")
    if isinstance(raw, list):
        modules.extend(str(m).strip() for m in raw if str(m).strip())
    primary = str(case.get("module") or "").strip()
    if primary and primary not in modules:
        modules.append(primary)
    return modules
