"""供 Admin/MOA/Tunnel 等模块安全导入 project.loader。"""

from __future__ import annotations

import sys
from pathlib import Path

_PLATFORM_DIR = Path(__file__).resolve().parent.parent


def ensure_platform_importable() -> Path:
    if str(_PLATFORM_DIR) not in sys.path:
        sys.path.insert(0, str(_PLATFORM_DIR))
    return _PLATFORM_DIR


def module_path(key: str, default_relative: str) -> Path:
    ensure_platform_importable()
    from project.loader import path_key

    return path_key(key, default_relative)
