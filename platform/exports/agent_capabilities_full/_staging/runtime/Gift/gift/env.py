"""环境变量加载。"""

from __future__ import annotations

import os

from .paths import gift_dir


def load_local_env() -> None:
    """从 Gift/.env.local 读取环境变量（不覆盖已有变量）。"""
    env_path = os.path.join(gift_dir(), ".env.local")
    if not os.path.exists(env_path):
        return

    try:
        with open(env_path, "r", encoding="utf-8") as f:
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
