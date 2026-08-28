"""Web Agent 调用 Cursor SDK（复用 dingtalk_gateway cursor_runner）。"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parents[1] / "dingtalk_gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from bridge_manager import bridge_initialized, init_sdk_bridge  # noqa: E402
from code_modify_guard import guard_readonly_agent_reply  # noqa: E402
from code_modify_permission import (  # noqa: E402
    allow_moa_registry_in_readonly,
    code_modify_denial_message,
    looks_like_code_modify_request,
)
from source_file_guard import guard_readonly_source_file_reply  # noqa: E402
from source_file_permission import (  # noqa: E402
    STAFF_ID_ENV,
    looks_like_source_file_request,
    source_file_denial_message,
)
from adb_execution_guard import (  # noqa: E402
    adb_execution_denial_message_for_web,
    looks_like_adb_execution_request,
)
from online_env_guard import (  # noqa: E402
    resolve_online_env_denial,
)
from online_vip_notify import (  # noqa: E402
    looks_like_online_vip_request,
    online_vip_handoff_reply,
)
from cursor_runner import (  # noqa: E402
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_S,
    repo_cwd,
    run_agent_prompt_streaming,
)
from task_session import TaskSession  # noqa: E402
from user_agent_pool import get_user_agent_pool  # noqa: E402

from web_admin_permission import has_admin_permission  # noqa: E402
from web_prompt import build_web_prompt, normalize_reply_mode  # noqa: E402
from web_session_context import (  # noqa: E402
    build_continue_context_note,
    build_rotation_system_note,
    should_rotate_cursor_agent,
)
from web_session_store import get_session_store  # noqa: E402
from web_run_phases import (  # noqa: E402
    PHASE_BRIDGE_INIT,
    PHASE_PROMPT_BUILD,
)

logger = logging.getLogger("web-agent")

_BRIDGE_INIT = False


def ensure_bridge(*, on_phase: Callable[[str], None] | None = None) -> None:
    global _BRIDGE_INIT

    def _phase(line: str) -> None:
        if on_phase and line:
            on_phase(line)

    if _BRIDGE_INIT or bridge_initialized():
        _BRIDGE_INIT = True
        return
    _phase(PHASE_BRIDGE_INIT)
    init_sdk_bridge(repo_cwd())
    pool = get_user_agent_pool()
    pool.start_idle_sweeper()
    _BRIDGE_INIT = True


def run_web_chat(
    session_id: str,
    message: str,
    *,
    staff_id: str | None = None,
    requester_name: str | None = None,
    image_paths: list[str | Path] | None = None,
    file_paths: list[str | Path] | None = None,
    attachment_names: list[str] | None = None,
    on_render: Callable[[str], None],
    session_ctrl: TaskSession | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    model: str | None = None,
    enabled_external_agents: list[str] | None = None,
    reply_mode: str | None = None,
    on_phase: Callable[[str], None] | None = None,
) -> str:
    """在指定 Web 会话中运行 Agent，返回最终 assistant 文本。"""

    def _phase(line: str) -> None:
        if on_phase and line:
            on_phase(line)

    ensure_bridge(on_phase=on_phase)
    if session_ctrl:
        session_ctrl.check_cancelled()
    store = get_session_store()
    user_key = store.user_key(session_id)
    meta = store.get_session(session_id)
    is_new = meta is None or not meta.has_assistant
    image_list = list(image_paths or [])
    file_list = list(file_paths or [])

    code_allowed = has_admin_permission(staff_id=staff_id, permission="code_modify")
    source_allowed = has_admin_permission(staff_id=staff_id, permission="source_file")
    online_allowed = has_admin_permission(staff_id=staff_id, permission="online")
    allow_moa_registry = allow_moa_registry_in_readonly(code_modify_allowed=code_allowed)
    if looks_like_code_modify_request(message) and not code_allowed:
        return code_modify_denial_message()
    if looks_like_source_file_request(message) and not source_allowed:
        return source_file_denial_message()
    if looks_like_adb_execution_request(message):
        return adb_execution_denial_message_for_web()
    if looks_like_online_vip_request(message):
        return online_vip_handoff_reply(
            message=message,
            requester_staff_id=(staff_id or "").strip(),
            requester_name=(requester_name or "").strip(),
        )
    denial = resolve_online_env_denial(message, online_admin_allowed=online_allowed)
    if denial:
        return denial

    agent_message = message
    if should_rotate_cursor_agent(session_id):
        get_user_agent_pool().invalidate(user_key)
        rotation_note = build_rotation_system_note(session_id)
        if rotation_note:
            agent_message = f"{message.rstrip()}\n\n{rotation_note}"
        logger.info(
            "Web 会话 %s 过长，已轮换 Cursor Agent user_key=%s",
            session_id[:8],
            user_key,
        )
    else:
        continue_note = build_continue_context_note(session_id, message)
        if continue_note:
            agent_message = f"{message.rstrip()}\n\n{continue_note}"

    _phase(PHASE_PROMPT_BUILD)
    prompt = build_web_prompt(
        agent_message,
        is_new_session=is_new,
        session_id=session_id,
        batch_progress_key=user_key,
        image_count=len(image_list),
        file_paths=file_list,
        attachment_names=attachment_names,
        enabled_external_agents=enabled_external_agents,
        reply_mode=reply_mode,
        allow_code_modify=code_allowed,
        allow_moa_registry=allow_moa_registry,
        allow_online_env_operation=online_allowed,
        allow_online_public_query=True,
    )

    prev_staff_id = os.environ.get(STAFF_ID_ENV)
    if staff_id:
        os.environ[STAFF_ID_ENV] = staff_id
    try:
        raw = run_agent_prompt_streaming(
            prompt,
            image_paths=image_list,
            on_render=on_render,
            user_key=user_key,
            sender_name=f"Web-{session_id[:8]}",
            use_gateway_rules=False,
            allow_code_modify=code_allowed,
            allow_moa_registry=allow_moa_registry,
            session=session_ctrl,
            timeout_s=timeout_s,
            show_thinking=True,
            web_stream=True,
            include_process_in_final=normalize_reply_mode(reply_mode) == "detailed",
            model=model or DEFAULT_MODEL,
            on_phase=on_phase,
        )
    finally:
        if staff_id:
            if prev_staff_id is None:
                os.environ.pop(STAFF_ID_ENV, None)
            else:
                os.environ[STAFF_ID_ENV] = prev_staff_id
    guarded = guard_readonly_agent_reply(
        raw,
        allow_code_modify=code_allowed,
        allow_moa_registry=allow_moa_registry,
    )
    return guard_readonly_source_file_reply(
        guarded,
        allow_source_file=source_allowed,
    )
