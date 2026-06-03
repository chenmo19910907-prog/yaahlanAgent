"""从 YAML 与 Redis 加载 MOA 运行时配置。"""

from __future__ import annotations

import os
from typing import Any

from .paths import config_dir

_YAML_ENV_MAP: dict[str, str] = {
    "entry_url": "MOA_ENTRY_URL",
    "cookie": "MOA_COOKIE",
    "origin": "MOA_ORIGIN",
    "referer": "MOA_REFERER",
    "user_agent": "MOA_USER_AGENT",
    "request_source": "MOA_REQUEST_SOURCE",
}


def _yaml_config_path() -> str:
    return os.path.join(config_dir(), "moa.yaml")


def _load_yaml_dict(path: str) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as e:
        raise RuntimeError(
            "需要 PyYAML：请执行 MOA/.venv/bin/pip install -r MOA/requirements.txt"
        ) from e

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except OSError as e:
        raise RuntimeError(f"无法读取配置文件: {path}") from e
    except yaml.YAMLError as e:
        raise RuntimeError(f"YAML 解析失败: {path}") from e

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise RuntimeError(f"配置文件根节点必须是 mapping: {path}")
    return data


def _apply_moa_section(moa: dict[str, Any]) -> None:
    for yaml_key, env_key in _YAML_ENV_MAP.items():
        value = moa.get(yaml_key)
        if value is not None and str(value).strip():
            os.environ.setdefault(env_key, str(value).strip())


def _load_cookie_from_redis(redis_cfg: dict[str, Any]) -> None:
    if os.environ.get("MOA_COOKIE"):
        return
    if not redis_cfg.get("enabled"):
        return

    url = redis_cfg.get("url")
    if not url:
        raise RuntimeError("redis.enabled=true 但未配置 redis.url")

    key = str(redis_cfg.get("cookie_key") or "moa:cookie")
    timeout = float(redis_cfg.get("socket_timeout", 2))

    try:
        import redis
    except ImportError as e:
        raise RuntimeError(
            "需要 redis 包：请执行 MOA/.venv/bin/pip install -r MOA/requirements.txt"
        ) from e

    try:
        client = redis.from_url(
            str(url),
            socket_timeout=timeout,
            socket_connect_timeout=timeout,
        )
        value = client.get(key)
    except redis.RedisError as e:
        raise RuntimeError(f"从 Redis 读取 MOA Cookie 失败: {e}") from e

    if value is None:
        raise RuntimeError(f"Redis 键不存在或为空: {key}")

    cookie = value.decode("utf-8", errors="replace").strip() if isinstance(value, bytes) else str(value).strip()
    if not cookie:
        raise RuntimeError(f"Redis 键为空: {key}")

    os.environ.setdefault("MOA_COOKIE", cookie)


def load_runtime_config() -> None:
    """加载 MOA 运行时配置（YAML + 可选 Redis），不覆盖已有环境变量。"""
    cfg_path = _yaml_config_path()
    if not os.path.exists(cfg_path):
        return

    root = _load_yaml_dict(cfg_path)
    moa = root.get("moa")
    if isinstance(moa, dict):
        _apply_moa_section(moa)

    redis_cfg = root.get("redis")
    if isinstance(redis_cfg, dict):
        _load_cookie_from_redis(redis_cfg)
