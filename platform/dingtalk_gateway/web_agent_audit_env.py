"""钉钉 Agent 运行时注入 Web 操作审计环境变量（MOA/Admin/风控落库）。"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass

from source_file_permission import DINGTALK_STAFF_ID_ENV

RUN_ID_ENV = "WEB_AGENT_RUN_ID"
CALLER_STAFF_ENV = "WEB_AGENT_CALLER_STAFF_ID"
CALLER_NAME_ENV = "WEB_AGENT_CALLER_NAME"

_RUN_ID_SAFE_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def make_dingtalk_run_id(message_id: str | None = None) -> str:
    raw = (message_id or "").strip()
    if raw:
        safe = _RUN_ID_SAFE_RE.sub("", raw)[:48]
        if safe:
            return f"dingtalk:{safe}"
    return f"dingtalk:{uuid.uuid4().hex[:12]}"


@dataclass
class WebAgentAuditEnvSnapshot:
    prev_run_id: str | None
    prev_caller_staff: str | None
    prev_caller_name: str | None
    set_run_id: bool
    set_caller_staff: bool
    set_caller_name: bool


def push_web_agent_audit_env(
    *,
    user_key: str | None,
    sender_name: str | None = None,
    sender_staff_id: str | None = None,
    run_id_hint: str | None = None,
) -> WebAgentAuditEnvSnapshot | None:
    """有 user_key 时补全审计 env；已有 WEB_AGENT_RUN_ID 时不覆盖（Web worker）。"""
    if not (user_key or "").strip():
        return None

    prev_run = os.environ.get(RUN_ID_ENV)
    prev_staff = os.environ.get(CALLER_STAFF_ENV)
    prev_name = os.environ.get(CALLER_NAME_ENV)

    set_run = False
    set_staff = False
    set_name = False

    if not (prev_run or "").strip():
        os.environ[RUN_ID_ENV] = make_dingtalk_run_id(run_id_hint)
        set_run = True

    staff = (sender_staff_id or os.environ.get(DINGTALK_STAFF_ID_ENV) or "").strip()
    if staff and not (os.environ.get(CALLER_STAFF_ENV) or "").strip():
        os.environ[CALLER_STAFF_ENV] = staff
        set_staff = True

    name = (sender_name or "").strip()
    if name and not (os.environ.get(CALLER_NAME_ENV) or "").strip():
        os.environ[CALLER_NAME_ENV] = name
        set_name = True

    if not (set_run or set_staff or set_name):
        return None

    return WebAgentAuditEnvSnapshot(
        prev_run_id=prev_run,
        prev_caller_staff=prev_staff,
        prev_caller_name=prev_name,
        set_run_id=set_run,
        set_caller_staff=set_staff,
        set_caller_name=set_name,
    )


def pop_web_agent_audit_env(snapshot: WebAgentAuditEnvSnapshot | None) -> None:
    if snapshot is None:
        return

    def _restore(key: str, prev: str | None, *, did_set: bool) -> None:
        if not did_set:
            return
        if prev is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prev

    _restore(RUN_ID_ENV, snapshot.prev_run_id, did_set=snapshot.set_run_id)
    _restore(CALLER_STAFF_ENV, snapshot.prev_caller_staff, did_set=snapshot.set_caller_staff)
    _restore(CALLER_NAME_ENV, snapshot.prev_caller_name, did_set=snapshot.set_caller_name)
