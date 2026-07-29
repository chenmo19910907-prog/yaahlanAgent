#!/usr/bin/env python3
"""验证 MDP Agent 查询脚本解析逻辑。"""

from __future__ import annotations

import sys
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from middleware_agent_query import (  # noqa: E402
    _clean_reply,
    _collect_chat_result,
    _extract_task_id,
    _parse_ndjson_events,
    resolve_base_url,
)


def main() -> int:
    events = _parse_ndjson_events(
        '{"type":"done","reply":"hello","session_id":"abc"}\n'
        '{"type":"tool_start","tool":"x"}\n'
    )
    assert len(events) == 2
    assert events[0]["type"] == "done"

    reply = (
        "已启动\n\n"
        '_task_handoff:{"task_id": "t-1", "title": "demo"}_\n'
    )
    assert _extract_task_id(reply) == "t-1"

    cleaned = _clean_reply(
        '_thinking:{"steps": [{"label": "x", "content": "y"}]}_\n\nhello'
    )
    assert cleaned == "hello"

    events = _parse_ndjson_events(
        '{"type":"reply_delta","delta":"你"}\n'
        '{"type":"done","reply":"你好","session_id":"s1"}\n'
    )
    answer, sid = _collect_chat_result(events, None)
    assert answer == "你好"
    assert sid == "s1"

    url = resolve_base_url("http://example.com/")
    assert url == "http://example.com"

    print("verify_middleware_agent_query: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
