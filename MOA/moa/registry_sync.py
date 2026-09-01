"""MOA 试跑成功后，为未登记模板自动入库 registry 并刷新工具工作台。"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Any

from .paths import moa_dir, registry_path, templates_dir

_REPO_ROOT = os.path.dirname(moa_dir())
_PLATFORM_CATALOG_HOOK = os.path.join(
    _REPO_ROOT, "platform", "scripts", "after_registry_update.py"
)


def _read_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} 必须是 JSON object")
    return data


def _template_ref_patterns() -> list[re.Pattern[str]]:
    bases = {"MOA/templates", os.path.basename(templates_dir())}
    bases.add(os.path.relpath(templates_dir(), moa_dir()).replace("\\", "/"))
    return [re.compile(rf"{re.escape(base)}/([^\s\"'\\]+)") for base in sorted(bases)]


def _collect_registered_templates() -> set[str]:
    registry = _read_json(registry_path())
    items = registry.get("items")
    if not isinstance(items, list):
        raise ValueError("registry.items 必须是 array")
    registered: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        cmd = item.get("command")
        if not isinstance(cmd, str):
            continue
        for pattern in _template_ref_patterns():
            for match in pattern.finditer(cmd):
                registered.add(match.group(1))
    return registered


def template_basename_from_payload_file(payload_file: str | None) -> str | None:
    if not payload_file:
        return None
    path = os.path.abspath(os.path.realpath(payload_file))
    root = os.path.abspath(os.path.realpath(templates_dir()))
    if not (path == root or path.startswith(root + os.sep)):
        return None
    fname = os.path.basename(path)
    if not fname.endswith(".json"):
        return None
    return fname


def template_needs_sync(fname: str) -> bool:
    return fname not in _collect_registered_templates()


def refresh_platform_workbench(*, quiet: bool = True) -> None:
    """registry 变更后刷新 platform/catalog.html（工具工作台能力清单）。"""
    if not os.path.isfile(_PLATFORM_CATALOG_HOOK):
        raise RuntimeError(f"未找到工具台刷新脚本: {_PLATFORM_CATALOG_HOOK}")
    cmd = [sys.executable, _PLATFORM_CATALOG_HOOK]
    if quiet:
        cmd.append("--quiet")
    result = subprocess.run(cmd, cwd=_REPO_ROOT, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"刷新工具工作台失败，退出码 {result.returncode}")


def auto_sync_registry_after_success(payload_file: str | None) -> bool:
    """未登记模板试跑成功后执行 sync_registry 并刷新工具工作台；已登记或无模板则跳过。"""
    fname = template_basename_from_payload_file(payload_file)
    if not fname:
        return False
    if not template_needs_sync(fname):
        return False

    script = os.path.join(moa_dir(), "scripts", "sync_registry.py")
    print(f"auto_sync_registry: 试跑成功，正在为 {fname} 自动入库…", file=sys.stderr)
    result = subprocess.run([sys.executable, script], check=False)
    if result.returncode != 0:
        raise RuntimeError(f"sync_registry 退出码 {result.returncode}")
    # sync_registry 已跑 generate_index；再显式刷新 catalog，确保工作台立即生效
    refresh_platform_workbench(quiet=True)
    print(
        "auto_sync_registry: 已入库并刷新工具工作台（MOA/使用方法.md + platform/catalog.html）",
        file=sys.stderr,
    )
    return True
