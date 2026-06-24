"""未激活 MOA/.venv 时，自动注入 site-packages 或切换到 venv 解释器。"""

from __future__ import annotations

import os
import sys

from .paths import moa_dir


def _venv_python_path() -> str | None:
    if sys.platform == "win32":
        candidate = os.path.join(moa_dir(), ".venv", "Scripts", "python.exe")
    else:
        candidate = os.path.join(moa_dir(), ".venv", "bin", "python3")
    return candidate if os.path.isfile(candidate) else None


def ensure_moa_venv() -> None:
    """使 MOA/.venv 中的依赖（PyYAML、redis 等）对当前进程可用。"""
    venv_root = os.path.join(moa_dir(), ".venv")
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
