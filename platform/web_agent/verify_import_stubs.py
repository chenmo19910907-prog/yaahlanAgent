"""单测导入 server 前注入 cursor_runner / cursor_sdk 桩，避免依赖本机 venv。"""

from __future__ import annotations

import sys
import types
from unittest import mock


def stub_cursor_runner() -> None:
    if "cursor_runner" in sys.modules:
        return

    sdk = types.ModuleType("cursor_sdk")
    for name in (
        "Agent",
        "AgentOptions",
        "CursorAgentError",
        "LocalAgentOptions",
        "SDKImage",
        "UserMessage",
    ):
        setattr(sdk, name, mock.MagicMock())
    sdk_client = types.ModuleType("cursor_sdk._client")
    sdk_client._default_client = None
    sdk_client.close_default_client = lambda: None
    sys.modules["cursor_sdk"] = sdk
    sys.modules["cursor_sdk._client"] = sdk_client

    bridge = types.ModuleType("bridge_manager")
    bridge.bridge_initialized = mock.MagicMock(return_value=False)
    bridge.init_sdk_bridge = mock.MagicMock()
    sys.modules["bridge_manager"] = bridge

    runner = mock.MagicMock()
    runner.DEFAULT_MODEL = "composer-2.5"
    runner.resolve_agent_timeout_s = mock.MagicMock(return_value=3600)
    sys.modules["cursor_runner"] = runner
