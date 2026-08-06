"""MOA/scripts 侧读取 AGENT_PROJECT 路径与 execute。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PLATFORM = _REPO / "platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from project.loader import get_repo_root  # noqa: E402
from project.repo_paths import (  # noqa: E402
    batch_progress_script,
    gateway_dir,
    gift_execute_path,
    gift_module_dir,
    moa_execute_path,
    moa_module_dir,
    moa_template,
    moa_templates_dir,
    mse_execute_path,
    tmp_dir,
    workflow_execute_path,
)

repo_root = get_repo_root


def moa_templates_repo_rel() -> str:
    """paths.moaTemplates 相对仓库根的路径（写入 registry command 用）。"""
    from project.loader import get_project_config

    paths = get_project_config().get("paths")
    if isinstance(paths, dict):
        raw = str(paths.get("moaTemplates") or "").strip()
        if raw:
            return raw.replace("\\", "/")
    return "MOA/templates"


def moa_template_repo_rel(name: str) -> str:
    return f"{moa_templates_repo_rel().rstrip('/')}/{name}"


def moa_execute_repo_rel() -> str:
    return os.path.relpath(str(moa_execute_path()), str(get_repo_root())).replace("\\", "/")


def dingtalk_excel_python() -> Path:
    return get_repo_root() / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel/venv/bin/python3.13"


def ensure_moa_gift_paths() -> None:
    for p in (moa_module_dir(), gift_module_dir()):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)


def ensure_gateway_path() -> Path:
    gw = gateway_dir()
    s = str(gw)
    if s not in sys.path:
        sys.path.insert(0, s)
    return gw


__all__ = [
    "batch_progress_script",
    "dingtalk_excel_python",
    "ensure_gateway_path",
    "ensure_moa_gift_paths",
    "gateway_dir",
    "gift_execute_path",
    "gift_module_dir",
    "moa_execute_path",
    "moa_execute_repo_rel",
    "moa_module_dir",
    "moa_template",
    "moa_template_repo_rel",
    "moa_templates_dir",
    "moa_templates_repo_rel",
    "mse_execute_path",
    "repo_root",
    "tmp_dir",
    "workflow_execute_path",
]
