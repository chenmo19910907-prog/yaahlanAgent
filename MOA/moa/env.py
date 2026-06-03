"""环境变量加载。"""

from __future__ import annotations

import os


def load_local_env(base_dir: str) -> None:
    """从 MOA/.env.local 读取环境变量（不覆盖已有变量）。"""
    env_path = os.path.join(base_dir, ".env.local")
    if not os.path.exists(env_path):
        return

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                if k:
                    os.environ.setdefault(k, v)
    except OSError:
        return

    from .runtime_config import load_runtime_config

    load_runtime_config()
