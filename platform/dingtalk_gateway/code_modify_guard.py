"""Agent 回复后置检查：只读账号不应实际改动代码。"""

from __future__ import annotations

import re

from code_modify_permission import CODE_ACTION_RE, CODE_PATH_RE

_GATEWAY_PATH_RE = re.compile(
    r"(dingtalk[_-]?gateway|platform/dingtalk|\bgateway\b|\.cursor/|gateway_prompt|"
    r"cursor_runner|command_router|bridge_manager)",
    re.I,
)
_MOA_REGISTRY_PATH_RE = re.compile(
    r"(MOA/templates|MOA/config/registry|MOA/使用方法|sync_registry\.py)",
    re.I,
)

_GUARD_SUFFIX = (
    "\n\n⚠️ 检测到回复涉及代码/网关改动描述；当前账号为只读模式，"
    "请人工确认仓库是否被实际修改。"
)


def _mentions_gateway_code_change(text: str) -> bool:
    if not CODE_PATH_RE.search(text) or not CODE_ACTION_RE.search(text):
        return False
    if _GATEWAY_PATH_RE.search(text):
        return True
    if _MOA_REGISTRY_PATH_RE.search(text):
        return False
    return True


def guard_readonly_agent_reply(
    reply: str,
    *,
    allow_code_modify: bool,
    allow_moa_registry: bool = False,
) -> str:
    if allow_code_modify:
        return reply
    text = (reply or "").strip()
    if not text:
        return reply
    if allow_moa_registry and _MOA_REGISTRY_PATH_RE.search(text):
        if not _GATEWAY_PATH_RE.search(text):
            return reply
    if _mentions_gateway_code_change(text):
        return text + _GUARD_SUFFIX
    return reply
