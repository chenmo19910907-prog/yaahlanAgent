"""加载 platform/dingtalk_gateway/.env.local 到 os.environ。"""

from __future__ import annotations

import os
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parent
ENV_LOCAL = GATEWAY_DIR / ".env.local"


def load_env_local() -> None:
    if not ENV_LOCAL.is_file():
        return
    for raw_line in ENV_LOCAL.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        # 始终以 .env.local 为准，便于运行中切换卡片模式等配置而无需重启进程
        if key:
            os.environ[key] = value


def require_env(name: str) -> str:
    load_env_local()
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"缺少环境变量 {name}，请在 {ENV_LOCAL} 配置（可参考 .env.example）"
        )
    return value
