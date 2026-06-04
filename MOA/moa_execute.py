#!/usr/bin/env python3
"""MOA httpproxy 本地执行入口（兼容原有调用方式）。"""

from __future__ import annotations

import os
import sys

_MOA_DIR = os.path.dirname(os.path.abspath(__file__))


def _venv_python_path() -> str | None:
    if sys.platform == "win32":
        candidate = os.path.join(_MOA_DIR, ".venv", "Scripts", "python.exe")
    else:
        candidate = os.path.join(_MOA_DIR, ".venv", "bin", "python3")
    return candidate if os.path.isfile(candidate) else None


def _ensure_moa_venv() -> None:
    """未激活 MOA/.venv 时，自动加载其 site-packages（或换用 venv 解释器）。"""
    venv_root = os.path.join(_MOA_DIR, ".venv")
    if not os.path.isdir(venv_root):
        return

    if os.path.realpath(sys.prefix) == os.path.realpath(venv_root):
        return

    py_tag = f"python{sys.version_info.major}.{sys.version_info.minor}"
    site_packages = os.path.join(venv_root, "lib", py_tag, "site-packages")
    if os.path.isdir(site_packages):
        if site_packages not in sys.path:
            sys.path.insert(0, site_packages)
        return

    venv_py = _venv_python_path()
    if venv_py and os.path.realpath(sys.executable) != os.path.realpath(venv_py):
        os.execv(venv_py, [venv_py, *sys.argv])

    raise RuntimeError(
        f"MOA/.venv 与当前 Python {sys.version_info.major}.{sys.version_info.minor} 不匹配。"
        f"请执行: python3 -m venv MOA/.venv && MOA/.venv/bin/pip install -r MOA/requirements.txt"
    )


_ensure_moa_venv()

sys.path.insert(0, _MOA_DIR)

from moa.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
