"""Agent 回复后置检查：只读账号不应实际改动代码。"""

from __future__ import annotations

from code_modify_permission import CODE_ACTION_RE, CODE_PATH_RE

_GUARD_SUFFIX = (
    "\n\n⚠️ 检测到回复涉及代码/网关改动描述；当前账号为只读模式，"
    "请人工确认仓库是否被实际修改。"
)


def guard_readonly_agent_reply(reply: str, *, allow_code_modify: bool) -> str:
    if allow_code_modify:
        return reply
    text = (reply or "").strip()
    if not text:
        return reply
    if CODE_PATH_RE.search(text) and CODE_ACTION_RE.search(text):
        return text + _GUARD_SUFFIX
    return reply
