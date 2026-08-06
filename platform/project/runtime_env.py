"""子进程继承 AGENT_PROJECT，保证 Web Agent / 网关 / MOA 等同项目。"""

from __future__ import annotations

import os
from typing import Mapping

from .loader import get_project_config, get_project_id


def project_env() -> dict[str, str]:
    raw = os.environ.get("AGENT_PROJECT") or os.environ.get("PROJECT") or ""
    pid = str(raw).strip() or get_project_id()
    return {"AGENT_PROJECT": pid, "PROJECT": pid}


def merge_project_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    merged = dict(os.environ)
    if env:
        merged.update({str(k): str(v) for k, v in env.items()})
    merged.update(project_env())
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
