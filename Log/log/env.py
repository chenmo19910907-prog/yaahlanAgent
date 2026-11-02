"""环境变量加载。"""

from __future__ import annotations

import os

from .paths import log_dir


def _load_env_file(path: str) -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
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
    _load_env_file(os.path.join(log_dir(), ".env.local"))
