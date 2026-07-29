#!/usr/bin/env python3
"""验证外部 Agent 配置与 prompt 注入。"""

from __future__ import annotations

import sys
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from external_agent_config import (  # noqa: E402
    default_enabled_external_agent_ids,
    external_agents_from_config,
    resolve_enabled_external_agent_ids,
)
from web_prompt import build_web_prompt  # noqa: E402


def main() -> int:
    agents = external_agents_from_config()
    assert agents, "config.json 应包含 externalAgents"
    assert any(item.get("defaultEnabled") for item in agents), "至少一个外部 Agent 默认启用"
    assert any(item.get("id") == "mdp_middleware" for item in agents), "应包含 MDP Agent"

    defaults = default_enabled_external_agent_ids()
    assert defaults, "defaultEnabled 解析失败"
    assert "mdp_middleware" not in defaults, defaults

    enabled = resolve_enabled_external_agent_ids(["yaahlan_service"])
    assert enabled == ["yaahlan_service"], enabled

    enabled_both = resolve_enabled_external_agent_ids(["yaahlan_service", "mdp_middleware"])
    assert enabled_both == ["yaahlan_service", "mdp_middleware"], enabled_both

    disabled = resolve_enabled_external_agent_ids([])
    assert disabled == [], disabled

    prompt_enabled = build_web_prompt(
        "查 provideDiamond MOA",
        is_new_session=True,
        enabled_external_agents=defaults,
    )
    assert "service_agent_query.py" in prompt_enabled
    assert "服务端 Agent" in prompt_enabled
    assert "middleware_agent_query.py" in prompt_enabled
    assert "未勾选（禁止调用）" in prompt_enabled
    assert "即使用户消息里点名" in prompt_enabled

    prompt_middleware = build_web_prompt(
        "查 MDP MOA",
        is_new_session=True,
        enabled_external_agents=["mdp_middleware"],
    )
    assert "middleware_agent_query.py" in prompt_middleware
    assert "MDP Agent" in prompt_middleware
    assert "service_agent_query.py" in prompt_middleware
    assert "未勾选（禁止调用）" in prompt_middleware
    assert "即使用户消息里点名" in prompt_middleware

    prompt_continue = build_web_prompt(
        "使用MDP agent查询VIP",
        is_new_session=False,
        enabled_external_agents=["yaahlan_service"],
    )
    assert "当前已勾选外部 Agent：服务端 Agent" in prompt_continue
    assert "未勾选 MDP Agent" in prompt_continue
    assert "即使用户消息点名也不得调用" in prompt_continue

    prompt_disabled = build_web_prompt(
        "查 provideDiamond MOA",
        is_new_session=True,
        enabled_external_agents=[],
    )
    assert "不得执行" in prompt_disabled or "禁止调用" in prompt_disabled
    assert "service_agent_query.py" in prompt_disabled
    assert "middleware_agent_query.py" in prompt_disabled

    print("verify_external_agent_settings: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
