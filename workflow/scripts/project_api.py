"""workflow 脚本读取 AGENT_PROJECT API 与模块路径。"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PLATFORM = _REPO / "platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from project.loader import api_endpoint, get_repo_root, moa_generative_root, workflow_root  # noqa: E402
from project.repo_paths import moa_execute_path, moa_module_dir, moa_template, tmp_dir  # noqa: E402


def service_url(key: str, default: str) -> str:
    return api_endpoint(key, default)


def repo_root() -> Path:
    return get_repo_root()


__all__ = [
    "moa_execute_path",
    "moa_generative_root",
    "moa_module_dir",
    "moa_template",
    "repo_root",
    "service_url",
    "tmp_dir",
    "workflow_root",
]
