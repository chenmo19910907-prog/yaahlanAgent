"""外部 Agent 查询进度：脚本写入，Web Agent 轮询展示。"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from env_loader import GATEWAY_DIR
from progress_message import format_duration

PROGRESS_DIR = GATEWAY_DIR / "data" / "external_agent_progress"
USER_KEY_ENV = "WEB_AGENT_BATCH_KEY"


@dataclass(frozen=True)
class ExternalAgentProgressState:
    user_key: str
    agent_id: str
    agent_label: str
    status: str
    detail: str = ""
    started_at: float = 0.0
    updated_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_key": self.user_key,
            "agent_id": self.agent_id,
            "agent_label": self.agent_label,
            "status": self.status,
            "detail": self.detail,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }


def resolve_user_key(explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    return (os.environ.get(USER_KEY_ENV) or "").strip()


def _safe_filename(user_key: str) -> str:
    digest = hashlib.sha256(user_key.encode("utf-8")).hexdigest()[:24]
    return f"{digest}.json"


def _progress_path(user_key: str) -> Path:
    return PROGRESS_DIR / _safe_filename(user_key)


def _preview(text: str, *, limit: int = 48) -> str:
    line = " ".join((text or "").split())
    if not line:
        return ""
    if len(line) <= limit:
        return line
    return line[: limit - 1] + "…"


def report_external_agent_querying(
    user_key: str,
    *,
    agent_id: str,
    agent_label: str,
    message: str = "",
) -> ExternalAgentProgressState:
    key = (user_key or "").strip()
    if not key:
        raise ValueError("user_key 不能为空")
    now = time.time()
    existing = read_external_agent_progress(key)
    started_at = existing.started_at if existing and existing.status == "querying" else now
    state = ExternalAgentProgressState(
        user_key=key,
        agent_id=(agent_id or "").strip() or "external_agent",
        agent_label=(agent_label or "").strip() or "外部 Agent",
        status="querying",
        detail=_preview(message),
        started_at=started_at,
        updated_at=now,
    )
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    _progress_path(key).write_text(
        json.dumps(state.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return state


def report_external_agent_error(
    user_key: str,
    *,
    agent_id: str,
    agent_label: str,
    error: str,
) -> ExternalAgentProgressState:
    key = (user_key or "").strip()
    if not key:
        raise ValueError("user_key 不能为空")
    now = time.time()
    existing = read_external_agent_progress(key)
    state = ExternalAgentProgressState(
        user_key=key,
        agent_id=(agent_id or "").strip() or "external_agent",
        agent_label=(agent_label or "").strip() or "外部 Agent",
        status="error",
        detail=_preview(error, limit=120),
        started_at=existing.started_at if existing else now,
        updated_at=now,
    )
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    _progress_path(key).write_text(
        json.dumps(state.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return state


def read_external_agent_progress(user_key: str) -> ExternalAgentProgressState | None:
    key = (user_key or "").strip()
    if not key:
        return None
    path = _progress_path(key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return ExternalAgentProgressState(
        user_key=str(data.get("user_key") or key),
        agent_id=str(data.get("agent_id") or ""),
        agent_label=str(data.get("agent_label") or ""),
        status=str(data.get("status") or ""),
        detail=str(data.get("detail") or ""),
        started_at=float(data.get("started_at") or 0.0),
        updated_at=float(data.get("updated_at") or 0.0),
    )


def clear_external_agent_progress(user_key: str) -> None:
    key = (user_key or "").strip()
    if not key:
        return
    path = _progress_path(key)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def build_external_agent_progress_message(state: ExternalAgentProgressState | None) -> str:
    if state is None:
        return ""
    label = state.agent_label or "外部 Agent"
    if state.status == "querying":
        elapsed = max(0.0, time.time() - (state.started_at or state.updated_at or time.time()))
        body = f"{label} 查询中（已 {format_duration(elapsed)}）"
        if state.detail:
            body += f"：{state.detail}"
        return f"{body}…"
    if state.status == "error":
        detail = state.detail or "未知错误"
        return f"{label} 查询失败：{detail}"
    return ""
