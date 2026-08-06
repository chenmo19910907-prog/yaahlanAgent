"""adb/scripts 侧读取 AGENT_PROJECT 路径。"""

from __future__ import annotations

import sys
from pathlib import Path

_ADB = Path(__file__).resolve().parents[1]
if str(_ADB) not in sys.path:
    sys.path.insert(0, str(_ADB))

from adb.project_paths import (  # noqa: E402
    adb_scripts_root,
    admin_execute_path,
    moa_execute_path,
    repo_root,
)

__all__ = [
    "adb_execute_path",
    "adb_scripts_root",
    "admin_execute_path",
    "moa_execute_path",
    "repo_root",
]


def adb_execute_path() -> Path:
    return repo_root() / "adb" / "adb_execute.py"
