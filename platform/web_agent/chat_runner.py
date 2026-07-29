"""Web Agent 调用 Cursor SDK（复用 dingtalk_gateway cursor_runner）。"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parents[1] / "dingtalk_gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from bridge_manager import init_sdk_bridge  # noqa: E402
from cursor_runner import (  # noqa: E402
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_S,
    repo_cwd,
    run_agent_prompt_streaming,
)
from task_session import TaskSession  # noqa: E402
from user_agent_pool import get_user_agent_pool  # noqa: E402

from web_prompt import build_web_prompt  # noqa: E402
from web_session_store import get_session_store  # noqa: E402

logger = logging.getLogger("web-agent")

_BRIDGE_INIT = False


def ensure_bridge() -> None:
    global _BRIDGE_INIT
    if not _BRIDGE_INIT:
        init_sdk_bridge(repo_cwd())
        pool = get_user_agent_pool()
        pool.start_idle_sweeper()
        _BRIDGE_INIT = True


def run_web_chat(
    session_id: str,
    message: str,
    *,
    image_paths: list[str | Path] | None = None,
    file_paths: list[str | Path] | None = None,
    attachment_names: list[str] | None = None,
    on_render: Callable[[str], None],
    session_ctrl: TaskSession | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    model: str | None = None,
    enabled_external_agents: list[str] | None = None,
) -> str:
    """在指定 Web 会话中运行 Agent，返回最终 assistant 文本。"""
    ensure_bridge()
    if session_ctrl:
        session_ctrl.check_cancelled()
    store = get_session_store()
    user_key = store.user_key(session_id)
    prior_messages = store.get_messages(session_id)
    is_new = not any(m.role == "assistant" for m in prior_messages)
    image_list = list(image_paths or [])
    file_list = list(file_paths or [])

    prompt = build_web_prompt(
        message,
        is_new_session=is_new,
        batch_progress_key=user_key,
        image_count=len(image_list),
        file_paths=file_list,
        attachment_names=attachment_names,
        enabled_external_agents=enabled_external_agents,
    )

    return run_agent_prompt_streaming(
        prompt,
        image_paths=image_list,
        on_render=on_render,
        user_key=user_key,
        sender_name=f"Web-{session_id[:8]}",
        use_gateway_rules=False,
        allow_code_modify=True,
        session=session_ctrl,
        timeout_s=timeout_s,
        show_thinking=True,
        model=model or DEFAULT_MODEL,
    )
