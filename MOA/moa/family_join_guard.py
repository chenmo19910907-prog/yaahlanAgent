"""Agent 场景拦截 MOA joinFamily 后门（加入家族须走 Admin）。"""

from __future__ import annotations

import json
import os
import re
from typing import Any

_JOIN_FAMILY_BACKDOOR_RE = re.compile(r"joinFamily\s*\(", re.I)
_AGENT_BATCH_KEY_ENVS = ("WEB_AGENT_BATCH_KEY", "DINGTALK_AGENT_BATCH_KEY")


def agent_context_blocks_family_backdoor() -> bool:
    return any(str(os.environ.get(key) or "").strip() for key in _AGENT_BATCH_KEY_ENVS)


def payload_uses_family_join_backdoor(payload: dict[str, Any]) -> bool:
    url = str(payload.get("url") or "")
    if "user-backdoor" not in url:
        return False
    blob_parts: list[str] = [url, json.dumps(payload.get("params") or [], ensure_ascii=False)]
    blob = "\n".join(blob_parts)
    return bool(_JOIN_FAMILY_BACKDOOR_RE.search(blob))


def assert_agent_family_join_not_backdoor(payload: dict[str, Any]) -> None:
    if not agent_context_blocks_family_backdoor():
        return
    if not payload_uses_family_join_backdoor(payload):
        return
    raise ValueError(
        "Agent 场景禁止 MOA 后门 joinFamily；请改用 "
        "python3 Admin/admin_execute.py --add-family-member "
        "--family-id <familyId> --family-user-id <userId>"
    )
