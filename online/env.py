"""线上环境变量加载（Admin / MOA / Tunnel 共用）。"""

from __future__ import annotations

import os

from paths import env_local_path, online_dir, repo_root


def _load_env_file(path: os.PathLike[str] | str) -> None:
    env_path = os.fspath(path)
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


def load_online_env() -> None:
    """加载 `online/.env.local`；兼容旧路径 `*/.env.online.local`。"""
    _load_env_file(env_local_path())
    root = repo_root()
    for legacy in (
        root / "Admin" / ".env.online.local",
        root / "MOA" / ".env.online.local",
        root / "Tunnel" / ".env.online.local",
    ):
        _load_env_file(legacy)


def ensure_online_env() -> None:
    load_online_env()
