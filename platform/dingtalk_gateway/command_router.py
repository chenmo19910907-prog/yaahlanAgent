"""钉钉网关快捷指令：仅保留 Web Agent 重启（其余走 Cursor Agent）。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from route_patterns import WEB_AGENT_RESTART_RE
from web_agent_restart import force_restart_web_agent, format_force_restart_reply
from task_session import TaskSession

GATEWAY_DIR = Path(__file__).resolve().parent


@dataclass
class RoutedResult:
    handled: bool
    output: str = ""
    files: list[Path] = field(default_factory=list)
    task_kind: str = ""
    defer_web_agent_restart: bool = False


def try_route(user_text: str, session: TaskSession | None = None) -> RoutedResult:
    del session  # 重启路由不占用 TaskSession
    text = (user_text or "").strip()
    if not text:
        return RoutedResult(handled=False)

    if WEB_AGENT_RESTART_RE.match(text):
        if os.environ.get("WEB_AGENT_RUN_ID"):
            return RoutedResult(
                handled=True,
                output="",
                task_kind="web_agent_restart",
                defer_web_agent_restart=True,
            )
        outcome = force_restart_web_agent()
        return RoutedResult(
            handled=True,
            output=format_force_restart_reply(outcome),
            task_kind="web_agent_restart",
        )

    return RoutedResult(handled=False)
