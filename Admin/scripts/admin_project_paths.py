"""Admin/scripts 侧读取 AGENT_PROJECT 路径与模块 execute。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "scripts"
_PLATFORM = _REPO / "platform"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_repo_paths = _load_module("_repo_project_paths", _SCRIPTS / "project_paths.py")
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))
from project.repo_paths import (  # noqa: E402
    admin_execute_path,
    admin_module_dir,
    moa_execute_path,
    moa_module_dir,
)

admin_user_pool_paths = _repo_paths.admin_user_pool_paths
online_test_accounts_path = _repo_paths.online_test_accounts_path
repo_root = _repo_paths.repo_root
test_devices_json_path = _repo_paths.test_devices_json_path
testcase_kb_root = _repo_paths.testcase_kb_root

__all__ = [
    "admin_execute_path",
    "admin_module_dir",
    "admin_user_pool_paths",
    "moa_execute_path",
    "moa_module_dir",
    "online_test_accounts_path",
    "repo_root",
    "test_devices_json_path",
    "testcase_kb_root",
]
