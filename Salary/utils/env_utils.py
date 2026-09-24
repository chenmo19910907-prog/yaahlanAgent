# -*- coding: utf-8 -*-
"""加载项目 .env（不覆盖已存在的环境变量）。"""
from __future__ import annotations

import os


def load_env_file(project_root: str | None = None) -> str | None:
    root = project_root or os.getcwd()
    env_path = os.path.join(root, ".env")
    if not os.path.isfile(env_path):
        return None
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'\"")
            if key:
                os.environ.setdefault(key, val)
    return env_path
