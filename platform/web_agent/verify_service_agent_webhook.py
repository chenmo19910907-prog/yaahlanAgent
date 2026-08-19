#!/usr/bin/env python3
"""验证服务端 Agent Webhook 验签与等待逻辑。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from service_agent_webhook import (  # noqa: E402
    WEBHOOK_PATH,
    cleanup_task_wait,
    compute_webhook_signature,
    handle_webhook_body,
    notify_task_webhook,
    register_pending_task,
    resolve_callback_url,
    verify_webhook_signature,
    wait_for_webhook,
    webhook_mode_enabled,
)


def main() -> int:
    secret = "test-secret"
    body = json.dumps({"task_id": "task-42", "status": "completed"}, ensure_ascii=False).encode(
        "utf-8"
    )
    signature = compute_webhook_signature(body, secret)

    os.environ["YAAHLAN_SERVICE_AGENT_WEBHOOK_SECRET"] = secret
    os.environ["YAAHLAN_SERVICE_AGENT_WEBHOOK_URL"] = "https://example.test/api/service-agent/webhook"
    os.environ.pop("YAAHLAN_SERVICE_AGENT_USE_WEBHOOK", None)

    assert verify_webhook_signature(body, signature, secret)
    assert verify_webhook_signature(body, signature.split("=", 1)[1], secret)
    assert not verify_webhook_signature(body, "bad", secret)

    os.environ.pop("YAAHLAN_SERVICE_AGENT_USE_WEBHOOK", None)

    with patch("service_agent_webhook.callback_url_reachable", return_value=True), patch(
        "service_agent_webhook.resolve_webhook_secret", return_value=secret
    ):
        assert webhook_mode_enabled()
        assert resolve_callback_url() == "https://example.test/api/service-agent/webhook"
        assert WEBHOOK_PATH == "/api/service-agent/webhook"

        status, payload = handle_webhook_body(body, signature)
        assert status == 200
        assert payload.get("ok") is True

    register_pending_task("task-wait")
    notify_task_webhook("task-wait", "completed", {"task_id": "task-wait", "status": "completed"})
    assert wait_for_webhook("task-wait", 1.0) == "completed"
    cleanup_task_wait("task-wait")

    os.environ["YAAHLAN_SERVICE_AGENT_USE_WEBHOOK"] = "0"
    assert not webhook_mode_enabled()

    print("verify_service_agent_webhook: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
