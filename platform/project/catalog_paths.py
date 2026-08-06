"""工具台 catalog：按 AGENT_PROJECT 解析各模块 registry 路径。"""

from __future__ import annotations

from pathlib import Path

from .loader import (
    get_repo_root,
    moa_generative_root,
    moa_registry_path,
    path_key,
    workflow_root,
)

# sources.json modules[].id → (project.json paths 键, 仓库默认 registry 相对路径)
_MODULE_REGISTRY: dict[str, tuple[str, str]] = {
    "admin": ("adminRegistry", "Admin/config/registry.json"),
    "mse": ("mseRegistry", "MSE/config/registry.json"),
    "gift": ("giftRegistry", "Gift/config/registry.json"),
    "risk": ("riskRegistry", "Risk/config/registry.json"),
    "tunnel": ("tunnelRegistry", "Tunnel/config/registry.json"),
    "online": ("onlineRegistry", "online/config/registry.json"),
    "dingtalk": ("dingtalkRegistry", "DingTalk/config/registry.json"),
}


def module_registry_path(mod_id: str, default_relative: str) -> Path:
    """sources.json modules[].registry 的项目感知解析。"""
    pid = str(mod_id or "").strip().lower()
    rel = str(default_relative or "").strip()

    if pid == "moa":
        return moa_registry_path()

    if pid == "workflow":
        custom = workflow_root() / "config" / "registry.json"
        if custom.is_file():
            return custom

    if pid == "moa-generative":
        custom = moa_generative_root() / "config" / "registry.json"
        if custom.is_file():
            return custom

    entry = _MODULE_REGISTRY.get(pid)
    if entry:
        key, fallback = entry
        custom = path_key(key, fallback)
        if custom.is_file():
            return custom

    if not rel:
        raise ValueError(f"模块 {mod_id!r} 缺少 registry 路径")
    return get_repo_root() / rel


__all__ = ["module_registry_path"]
