"""服务端 Agent 异步任务落盘：支持同一 Web 会话并行多 task。"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TASK_STORE_DIR = Path(__file__).resolve().parent / "data" / "service_agent_tasks"
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


@dataclass(frozen=True)
class ServiceAgentTaskRecord:
    task_id: str
    user_key: str
    agent_id: str
    agent_label: str
    message_preview: str
    status: str
    conversation_id: str = ""
    result: str = ""
    error: str = ""
    submitted_at: float = 0.0
    updated_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_key": self.user_key,
            "agent_id": self.agent_id,
            "agent_label": self.agent_label,
            "message_preview": self.message_preview,
            "status": self.status,
            "conversation_id": self.conversation_id,
            "result": self.result,
            "error": self.error,
            "submitted_at": self.submitted_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServiceAgentTaskRecord:
        return cls(
            task_id=str(data.get("task_id") or ""),
            user_key=str(data.get("user_key") or ""),
            agent_id=str(data.get("agent_id") or ""),
            agent_label=str(data.get("agent_label") or ""),
            message_preview=str(data.get("message_preview") or ""),
            status=str(data.get("status") or ""),
            conversation_id=str(data.get("conversation_id") or ""),
            result=str(data.get("result") or ""),
            error=str(data.get("error") or ""),
            submitted_at=float(data.get("submitted_at") or 0.0),
            updated_at=float(data.get("updated_at") or 0.0),
        )


def _safe_filename(user_key: str) -> str:
    digest = hashlib.sha256(user_key.encode("utf-8")).hexdigest()[:24]
    return f"{digest}.json"


def _store_path(user_key: str) -> Path:
    return TASK_STORE_DIR / _safe_filename(user_key)


def _preview(text: str, *, limit: int = 48) -> str:
    line = " ".join((text or "").split())
    if not line:
        return ""
    if len(line) <= limit:
        return line
    return line[: limit - 1] + "…"


def _read_raw(user_key: str) -> dict[str, Any]:
    path = _store_path(user_key)
    if not path.is_file():
        return {"user_key": user_key, "tasks": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"user_key": user_key, "tasks": []}
    if not isinstance(data, dict):
        return {"user_key": user_key, "tasks": []}
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        tasks = []
    return {"user_key": str(data.get("user_key") or user_key), "tasks": tasks}


def _write_raw(user_key: str, tasks: list[dict[str, Any]]) -> None:
    TASK_STORE_DIR.mkdir(parents=True, exist_ok=True)
    _store_path(user_key).write_text(
        json.dumps(
            {"user_key": user_key, "tasks": tasks, "updated_at": time.time()},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def list_tasks(user_key: str) -> list[ServiceAgentTaskRecord]:
    key = (user_key or "").strip()
    if not key:
        return []
    raw = _read_raw(key)
    out: list[ServiceAgentTaskRecord] = []
    for item in raw.get("tasks") or []:
        if isinstance(item, dict):
            out.append(ServiceAgentTaskRecord.from_dict(item))
    return out


def get_task(user_key: str, task_id: str) -> ServiceAgentTaskRecord | None:
    tid = (task_id or "").strip()
    for record in list_tasks(user_key):
        if record.task_id == tid:
            return record
    return None


def register_task(
    user_key: str,
    *,
    task_id: str,
    agent_id: str,
    agent_label: str,
    message: str,
    conversation_id: str = "",
) -> ServiceAgentTaskRecord:
    key = (user_key or "").strip()
    tid = (task_id or "").strip()
    if not key or not tid:
        raise ValueError("user_key 与 task_id 不能为空")
    now = time.time()
    record = ServiceAgentTaskRecord(
        task_id=tid,
        user_key=key,
        agent_id=(agent_id or "").strip() or "yaahlan_service",
        agent_label=(agent_label or "").strip() or "服务端 Agent",
        message_preview=_preview(message),
        status="pending",
        conversation_id=(conversation_id or "").strip(),
        submitted_at=now,
        updated_at=now,
    )
    tasks = [item.as_dict() for item in list_tasks(key) if item.task_id != tid]
    tasks.append(record.as_dict())
    _write_raw(key, tasks)
    return record


def update_task(
    user_key: str,
    task_id: str,
    *,
    status: str | None = None,
    conversation_id: str | None = None,
    result: str | None = None,
    error: str | None = None,
) -> ServiceAgentTaskRecord | None:
    key = (user_key or "").strip()
    tid = (task_id or "").strip()
    tasks = list_tasks(key)
    updated: ServiceAgentTaskRecord | None = None
    rows: list[dict[str, Any]] = []
    now = time.time()
    for item in tasks:
        if item.task_id != tid:
            rows.append(item.as_dict())
            continue
        updated = ServiceAgentTaskRecord(
            task_id=item.task_id,
            user_key=item.user_key,
            agent_id=item.agent_id,
            agent_label=item.agent_label,
            message_preview=item.message_preview,
            status=status if status is not None else item.status,
            conversation_id=conversation_id if conversation_id is not None else item.conversation_id,
            result=result if result is not None else item.result,
            error=error if error is not None else item.error,
            submitted_at=item.submitted_at,
            updated_at=now,
        )
        rows.append(updated.as_dict())
    if updated is None:
        return None
    _write_raw(key, rows)
    return updated


def list_active_tasks(user_key: str) -> list[ServiceAgentTaskRecord]:
    return [item for item in list_tasks(user_key) if item.status not in TERMINAL_STATUSES]


def clear_tasks(user_key: str) -> None:
    key = (user_key or "").strip()
    if not key:
        return
    try:
        _store_path(key).unlink(missing_ok=True)
    except OSError:
        pass
