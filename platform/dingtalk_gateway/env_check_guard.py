"""钉钉网关：已取消群内「环境检查」快捷能力。"""

from __future__ import annotations

import re

# 仅整条消息为环境检查口令时拦截；自然语言问 Cookie/凭证不拦
ENV_CHECK_INTENT_RE = re.compile(
    r"^(?:"
    r"环境检查|"
    r"检查环境(?:配置)?|"
    r"doctor|"
    r"(?:@新手上手\.md\s+)?运行环境检查"
    r")\s*$",
    re.I,
)

_DOCTOR_OUTPUT_RE = re.compile(
    r"(?:环境检查未通过|环境检查已通过|【凭证有效性】|\[OK\]\s+钉钉文档 Cookie|\[FAIL\]\s+钉钉文档 Cookie)",
    re.I,
)

_DENY_MESSAGE = """\
钉钉群已取消「环境检查」功能。

• 只查 MOA 是否可用 → 发 `MOA检查`
• 本机全面自检 → 执行 `./platform/dingtalk_gateway/gateway_ctl.sh health`"""


def looks_like_env_check_request(text: str) -> bool:
    t = (text or "").strip()
    return bool(t) and bool(ENV_CHECK_INTENT_RE.match(t))


def env_check_denial_message() -> str:
    return _DENY_MESSAGE.strip()


def looks_like_doctor_output(text: str) -> bool:
    return bool(_DOCTOR_OUTPUT_RE.search(text or ""))


def guard_env_check_agent_reply(reply: str, *, prompt: str) -> str:
    """Agent 误跑 doctor 时兜底替换为取消说明。"""
    if not looks_like_env_check_request(prompt) and not looks_like_doctor_output(reply):
        return reply
    return env_check_denial_message()
