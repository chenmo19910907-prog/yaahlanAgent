"""环境变量加载。"""

from __future__ import annotations

import os

from .paths import e2e_dir


def _load_env_file(path: os.PathLike[str] | str) -> None:
    env_path = os.fspath(path)
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if key:
                    os.environ.setdefault(key, value.strip())
    except OSError:
        return


def load_local_env() -> None:
    base = e2e_dir()
    _load_env_file(base / ".env.local")
