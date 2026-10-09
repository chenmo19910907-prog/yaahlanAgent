#!/usr/bin/env python3
"""离线验证：钉钉 Agent 注入 WEB_AGENT_RUN_ID / 调用人环境变量。"""

from __future__ import annotations

import os
import sys

from web_agent_audit_env import (
    CALLER_NAME_ENV,
    CALLER_STAFF_ENV,
    RUN_ID_ENV,
    pop_web_agent_audit_env,
    push_web_agent_audit_env,
)


def main() -> int:
    errors: list[str] = []

    for key in (RUN_ID_ENV, CALLER_STAFF_ENV, CALLER_NAME_ENV):
        os.environ.pop(key, None)

    snap = push_web_agent_audit_env(
        user_key="cid:test:user:1",
        sender_name="武慧东",
        sender_staff_id="340506516327214715",
        run_id_hint="msgBZasBynhe8RG4o0UK8Ew",
    )
    if not os.environ.get(RUN_ID_ENV, "").startswith("dingtalk:"):
        errors.append("missing dingtalk run id")
    if os.environ.get(CALLER_STAFF_ENV) != "340506516327214715":
        errors.append("caller staff mismatch")
    if os.environ.get(CALLER_NAME_ENV) != "武慧东":
        errors.append("caller name mismatch")
    pop_web_agent_audit_env(snap)
    if any(os.environ.get(k) for k in (RUN_ID_ENV, CALLER_STAFF_ENV, CALLER_NAME_ENV)):
        errors.append("env not restored after pop")

    os.environ[RUN_ID_ENV] = "web-run-abc"
    os.environ[CALLER_STAFF_ENV] = "32274159141215328"
    os.environ[CALLER_NAME_ENV] = "陈墨"
    snap2 = push_web_agent_audit_env(
        user_key="web:sess",
        sender_name="其它",
        sender_staff_id="999",
        run_id_hint="x",
    )
    if os.environ.get(RUN_ID_ENV) != "web-run-abc":
        errors.append("overwrote existing run id")
    if os.environ.get(CALLER_STAFF_ENV) != "32274159141215328":
        errors.append("overwrote existing caller staff")
    pop_web_agent_audit_env(snap2)

    if errors:
        for item in errors:
            print(f"[FAIL] {item}", file=sys.stderr)
        return 1
    print("[OK] web_agent_audit_env")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
