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
    """从 MSE/.env.local 读取；Cookie 可回退 MOA/.env.local 的 MOA_COOKIE。"""
    _load_env_file(os.path.join(base_dir, ".env.local"))

    if os.environ.get("MSE_COOKIE", "").strip() or os.environ.get("MOA_COOKIE", "").strip():
        if not os.environ.get("MSE_COOKIE", "").strip() and os.environ.get("MOA_COOKIE", "").strip():
            os.environ.setdefault("MSE_COOKIE", os.environ["MOA_COOKIE"].strip())
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
                        os.environ.setdefault("MSE_COOKIE", cookie)
                        os.environ.setdefault("MOA_COOKIE", cookie)
                    break
    except OSError:
        return
