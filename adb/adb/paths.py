"""adb 包路径与运行时状态目录（随 AGENT_PROJECT 切换录制脚本根）。"""

from __future__ import annotations

from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent
ADB_ROOT = _PKG_ROOT
STATE_DIR = ADB_ROOT / ".state"
SCREENSHOTS_DIR = ADB_ROOT / "screenshots"


def scripts_root() -> Path:
    try:
        from .project_paths import adb_scripts_root

        return adb_scripts_root()
    except (ImportError, FileNotFoundError, ValueError, OSError):
        return ADB_ROOT / "录制脚本"


SCRIPTS_ROOT = scripts_root()


def ensure_state_dir() -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR


def script_abandon_path() -> Path:
    return ensure_state_dir() / "script_abandon.json"
