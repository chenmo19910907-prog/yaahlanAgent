"""子进程继承 AGENT_PROJECT，保证 Web Agent / 网关 / MOA 等同项目。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from .loader import get_project_config, get_project_id

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKER_ENV_FILES = (
    _REPO_ROOT / "Admin" / ".env.local",
    _REPO_ROOT / "MOA" / ".env.local",
    _REPO_ROOT / "Tunnel" / ".env.local",
    _REPO_ROOT / "platform" / "dingtalk_gateway" / ".env.local",
    _REPO_ROOT / "online" / ".env.local",
)


def project_env() -> dict[str, str]:
    raw = os.environ.get("AGENT_PROJECT") or os.environ.get("PROJECT") or ""
    pid = str(raw).strip() or get_project_id()
    return {"AGENT_PROJECT": pid, "PROJECT": pid}


def _read_env_file_override(path: Path, merged: dict[str, str]) -> None:
    if not path.is_file():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key:
                merged[key] = value.strip()
    except OSError:
        return


def merge_project_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    merged = dict(os.environ)
    if env:
        merged.update({str(k): str(v) for k, v in env.items()})
    merged.update(project_env())
    return merged


def merge_worker_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Worker 子进程环境：项目标识 + 各模块 .env.local 覆盖继承凭证（避免 shell 过期变量）。"""
    merged = merge_project_env(env)
    for env_path in _WORKER_ENV_FILES:
        _read_env_file_override(env_path, merged)
    return merged


def ensure_project_env(*, project_id: str | None = None) -> str:
    """写入 os.environ，供 Web Agent / 网关进程与子进程统一项目。"""
    pid = str(project_id or os.environ.get("AGENT_PROJECT") or os.environ.get("PROJECT") or "").strip()
    if not pid:
        pid = get_project_id()
    os.environ["AGENT_PROJECT"] = pid
    os.environ["PROJECT"] = pid
    get_project_config.cache_clear()
    return pid
