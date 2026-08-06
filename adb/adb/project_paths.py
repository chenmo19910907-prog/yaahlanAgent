"""ADB 模块读取 AGENT_PROJECT 路径与 MOA/Admin execute。"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PLATFORM = _REPO / "platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from project.loader import (  # noqa: E402
    adb_autotest_root,
    adb_scripts_root,
    get_project_id,
    get_repo_root,
    testcase_kb_root,
)
from project.repo_paths import (  # noqa: E402
    admin_execute_path,
    admin_module_dir,
    moa_execute_path,
    moa_module_dir,
    moa_template,
    moa_templates_dir,
)

repo_root = get_repo_root

__all__ = [
    "adb_autotest_root",
    "adb_scripts_root",
    "admin_execute_path",
    "admin_module_dir",
    "get_project_id",
    "moa_execute_path",
    "moa_module_dir",
    "moa_template",
    "moa_templates_dir",
    "repo_root",
    "testcase_kb_root",
]
