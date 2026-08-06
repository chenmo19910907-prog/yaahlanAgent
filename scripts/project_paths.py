"""scripts 侧读取 AGENT_PROJECT 路径（adb 模块勿依赖）。"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def repo_root() -> Path:
    return _REPO


def _ensure_platform() -> None:
    platform_dir = _REPO / "platform"
    if str(platform_dir) not in sys.path:
        sys.path.insert(0, str(platform_dir))


def testcase_kb_root() -> Path:
    _ensure_platform()
    from project.loader import testcase_kb_root as fn

    return fn()


def prd_kb_root() -> Path:
    _ensure_platform()
    from project.loader import prd_kb_root as fn

    return fn()


def bug_kb_root() -> Path:
    _ensure_platform()
    from project.loader import bug_kb_root as fn

    return fn()


def temporary_testcase_dir() -> Path:
    _ensure_platform()
    from project.loader import temporary_testcase_dir as fn

    return fn()


def test_devices_json_path() -> Path:
    _ensure_platform()
    from project.loader import test_devices_path

    return test_devices_path()


def online_test_accounts_path() -> Path:
    _ensure_platform()
    from project.loader import online_test_accounts_path as fn

    return fn()


def admin_user_pool_paths() -> tuple[Path, Path, Path]:
    """(legacy/inactive, inactive, active) admin user pool JSON paths."""
    kb = testcase_kb_root()
    return (
        kb / "admin_user_pool.json",
        kb / "admin_user_pool_inactive.json",
        kb / "admin_user_pool_active.json",
    )


def repo_relative_dir(path: Path, *, fallback: str) -> str:
    _ensure_platform()
    from project.loader import get_repo_root

    root = get_repo_root()
    try:
        rel = path.relative_to(root)
        text = str(rel).replace("\\", "/").rstrip("/")
        return f"{text}/"
    except ValueError:
        return f"{fallback.rstrip('/')}/"
