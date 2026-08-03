"""环境变量加载。"""

from __future__ import annotations

import os


def _load_env_file(env_path: str) -> None:
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


def load_local_env(base_dir: str) -> None:
    """从 Admin/.env.local 读取环境变量（不覆盖已有变量）。"""
    _load_env_file(os.path.join(base_dir, ".env.local"))


def load_online_env(base_dir: str) -> None:
    """从 online/.env.local 读取线上环境变量（兼容旧 */.env.online.local）。"""
    import sys

    repo = os.path.dirname(base_dir)
    online_path = os.path.join(repo, "online")
    if online_path not in sys.path:
        sys.path.insert(0, online_path)
    import env as online_env

    online_env.load_online_env()
