"""adb 包路径与运行时状态目录。"""

from __future__ import annotations

from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent
ADB_ROOT = _PKG_ROOT
STATE_DIR = ADB_ROOT / ".state"
SCRIPTS_ROOT = ADB_ROOT / "录制脚本"
SCREENSHOTS_DIR = ADB_ROOT / "screenshots"


def ensure_state_dir() -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR


def script_abandon_path() -> Path:
    return ensure_state_dir() / "script_abandon.json"
