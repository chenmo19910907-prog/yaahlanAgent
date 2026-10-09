"""MOA 执行后写入 Web Agent 调用记录（失败静默，不影响 MOA）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def _ensure_web_agent_path() -> None:
    repo = Path(__file__).resolve().parents[2]
    web_agent = repo / "platform" / "web_agent"
    path = str(web_agent)
    if path not in sys.path:
        sys.path.insert(0, path)


def try_record_moa_call(payload: dict[str, Any], response: dict[str, Any]) -> None:
    if os.environ.get("MOA_CALL_LOG_DISABLE", "").strip().lower() in ("1", "true", "yes"):
        return
    if not os.environ.get("WEB_AGENT_RUN_ID", "").strip():
        return
    try:
        _ensure_web_agent_path()
        from web_moa_call_log import _result_from_response, record_moa_call

        ok, _ = _result_from_response(response if isinstance(response, dict) else {})
        if not ok:
            return

        online = os.environ.get("ONLINE_ENV", "").strip().lower() in ("1", "true", "yes")
        record_moa_call(
            payload=payload,
            response=response,
            payload_file=os.environ.get("MOA_CALL_LOG_PAYLOAD_FILE", "").strip(),
            batch_key=os.environ.get("WEB_AGENT_BATCH_KEY", "").strip(),
            run_id=os.environ.get("WEB_AGENT_RUN_ID", "").strip(),
            operator_staff_id=os.environ.get("WEB_AGENT_CALLER_STAFF_ID", "").strip(),
            operator_name=os.environ.get("WEB_AGENT_CALLER_NAME", "").strip(),
            environment="online" if online else "test",
        )
    except Exception:  # noqa: BLE001
        return
