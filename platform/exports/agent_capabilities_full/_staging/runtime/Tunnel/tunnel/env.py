"""环境变量加载。"""

from __future__ import annotations

import os


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


def load_local_env(base_dir: str) -> None:
    """从 Tunnel/.env.local 读取；Cookie 可回退 MOA/.env.local 的 MOA_COOKIE。"""
    _load_env_file(os.path.join(base_dir, ".env.local"))

    if os.environ.get("TUNNEL_COOKIE", "").strip():
        return

    repo_root = os.path.dirname(base_dir)
    moa_env = os.path.join(repo_root, "MOA", ".env.local")
    if not os.path.exists(moa_env):
        return

    try:
        with open(moa_env, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if line.startswith("MOA_COOKIE="):
                    cookie = line.split("=", 1)[1].strip()
                    if cookie:
                        os.environ.setdefault("TUNNEL_COOKIE", cookie)
                    break
    except OSError:
        return


def load_online_env(base_dir: str) -> None:
    """从 online/.env.local 读取线上环境变量（兼容旧 */.env.online.local）。"""
    import sys

    repo = os.path.dirname(base_dir)
    online_path = os.path.join(repo, "online")
    if online_path not in sys.path:
        sys.path.insert(0, online_path)
    import env as online_env

    online_env.load_online_env()
