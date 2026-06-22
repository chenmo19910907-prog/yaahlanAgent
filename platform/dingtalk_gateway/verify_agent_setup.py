#!/usr/bin/env python3
"""验收网关无人值守配置：凭证 + MCP + SDK pong。"""

from __future__ import annotations

import sys

from cursor_runner import run_agent_prompt
from env_loader import load_env_local, require_env
from mcp_config import build_stdio_mcp_servers


def main() -> int:
    load_env_local()
    print("=== 钉钉网关 Agent 配置验收 ===")

    try:
        require_env("CURSOR_API_KEY")
        print("[OK] CURSOR_API_KEY")
    except RuntimeError as exc:
        print(f"[FAIL] {exc}")
        return 1

    mcps = build_stdio_mcp_servers()
    if mcps:
        print(f"[OK] MCP 已加载: {', '.join(mcps.keys())}")
    else:
        print("[WARN] 无可用 MCP（检查 .cursor/.mcp.secrets.json）")

    print("[INFO] 调用 SDK（本地 Agent）…")
    try:
        reply = run_agent_prompt(
            "只回复：gateway-ready，不要其它内容。",
            use_gateway_rules=False,
            enable_mcp=False,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] SDK: {exc}")
        return 1

    print(f"[OK] SDK 回复: {reply[:120]}")
    print("[OK] 网关 Agent 无人值守链路可用（无需 IDE 手动 Run）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
