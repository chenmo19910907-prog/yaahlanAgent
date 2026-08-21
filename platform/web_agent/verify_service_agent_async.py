#!/usr/bin/env python3
"""验证服务端 Agent 异步并行 task store 与进度聚合。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

GATEWAY_DIR = Path(__file__).resolve().parents[1] / "dingtalk_gateway"
WEB_AGENT_DIR = Path(__file__).resolve().parent
for path in (GATEWAY_DIR, WEB_AGENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from external_agent_progress import (  # noqa: E402
    build_external_agent_progress_message,
    clear_external_agent_progress,
    read_external_agent_progress,
    report_external_agent_multi_querying,
)
from service_agent_task_store import (  # noqa: E402
    clear_tasks,
    get_task,
    list_active_tasks,
    register_task,
    update_task,
)


def main() -> int:
    user_key = "web:test-service-agent-async"
    clear_tasks(user_key)
    clear_external_agent_progress(user_key)

    register_task(
        user_key,
        task_id="task-a",
        agent_id="yaahlan_service",
        agent_label="服务端 Agent",
        message="VIP 升级接口 ServiceUrl",
    )
    register_task(
        user_key,
        task_id="task-b",
        agent_id="yaahlan_service",
        agent_label="服务端 Agent",
        message="PK 结算取整规则",
    )
    assert len(list_active_tasks(user_key)) == 2

    report_external_agent_multi_querying(
        user_key,
        agent_label="服务端 Agent",
        details=["VIP 升级", "PK 结算"],
    )
    msg = build_external_agent_progress_message(read_external_agent_progress(user_key))
    assert "×2" in msg, msg
    assert "VIP" in msg, msg

    update_task(user_key, "task-a", status="completed", result="answer-a")
    assert get_task(user_key, "task-a").status == "completed"
    assert len(list_active_tasks(user_key)) == 1

    spawned: list[list[str]] = []

    def _fake_popen(cmd, **kwargs):  # noqa: ANN001
        spawned.append(list(cmd))
        class _Proc:
            pid = 99999

        return _Proc()

    with patch("service_agent_query._submit_task", return_value=("task-live", "conv-x")), patch(
        "service_agent_query._spawn_background_poller"
    ) as mock_spawn, patch("service_agent_query.resolve_token", return_value="yaahlan_ai_test"):
        from service_agent_query import submit_service_agent_async

        task_id, _ = submit_service_agent_async(
            "test question",
            token="yaahlan_ai_test",
            user_key=user_key,
            base_url="https://example.test",
        )
        assert task_id == "task-live"
        mock_spawn.assert_called_once()

    clear_tasks(user_key)
    clear_external_agent_progress(user_key)
    print("verify_service_agent_async: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
