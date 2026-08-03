#!/usr/bin/env python3
"""Web Agent 独立 worker：与 HTTP 服务解耦，服务重启不中断 Agent 执行。"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
PLATFORM_DIR = WEB_AGENT_DIR.parent
REPO_ROOT = PLATFORM_DIR.parent
GATEWAY_DIR = PLATFORM_DIR / "dingtalk_gateway"

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from batch_progress import clear_batch_progress  # noqa: E402
from cursor_runner import DEFAULT_TIMEOUT_S  # noqa: E402
from duration_history import classify_task_kind, get_duration_store  # noqa: E402
from progress_message import append_duration_footer  # noqa: E402
from task_session import TaskInterrupted, TaskSession  # noqa: E402
from user_agent_pool import get_user_agent_pool  # noqa: E402

from chat_runner import run_web_chat  # noqa: E402
from web_file_store import consume_pending_outputs  # noqa: E402
from web_run_store import (  # noqa: E402
    RUN_STATUS_DONE,
    RUN_STATUS_ERROR,
    RUN_STATUS_INTERRUPTED,
    RUN_STATUS_RUNNING,
    get_run_store,
)
from web_session_store import get_session_store  # noqa: E402

logger = logging.getLogger("web-agent-worker")

INTERRUPT_REPLY = "⚠️ 任务已中断。"
RETRY_HINT = "💡 原消息已回填到输入框，请检查后重试。"


class FileBackedTaskSession(TaskSession):
    """worker 子进程：从落盘 cancel 标记感知用户中断。"""

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self._run_id = run_id
        self._store = get_run_store()

    def check_cancelled(self) -> None:
        if self._store.is_cancel_requested(self._run_id):
            self.arm_cancel()
        super().check_cancelled()


def _emit(store, run_id: str, event: dict) -> None:
    store.append_event(run_id, event)


def _run_once(run_id: str) -> int:
    store = get_run_store()
    meta = store.get_run(run_id)
    if meta is None:
        logger.error("run %s 不存在", run_id)
        return 1
    if meta.status != RUN_STATUS_RUNNING:
        logger.info("run %s 状态=%s，跳过", run_id, meta.status)
        return 0

    session_store = get_session_store()
    session_id = meta.session_id
    user_key = session_store.user_key(session_id)
    task_kind = classify_task_kind(meta.message)
    session_ctrl = FileBackedTaskSession(run_id)
    session_ctrl.begin(
        meta.message or meta.display_message,
        conversation_id=user_key,
        budget_s=float(DEFAULT_TIMEOUT_S),
    )

    started_at = time.monotonic()
    last_markdown = ""
    status = "error"

    def on_render(markdown: str) -> None:
        nonlocal last_markdown
        last_markdown = markdown
        _emit(store, run_id, {"type": "delta", "markdown": markdown})

    def _append_assistant(text: str) -> None:
        output_files = consume_pending_outputs(session_id)
        session_store.append_message(
            session_id,
            "assistant",
            text,
            files=[item.to_message_dict() for item in output_files],
        )

    try:
        final = run_web_chat(
            session_id,
            meta.message,
            image_paths=meta.image_paths,
            file_paths=meta.file_paths,
            attachment_names=meta.attachment_names,
            on_render=on_render,
            session_ctrl=session_ctrl,
            model=meta.model or None,
            enabled_external_agents=meta.enabled_external_agents or None,
        )
        elapsed = time.monotonic() - started_at
        body = final or last_markdown
        final_text = append_duration_footer(body, elapsed, task_kind=task_kind)
        _append_assistant(final_text)
        _emit(store, run_id, {"type": "done", "text": final_text})
        store.mark_status(run_id, RUN_STATUS_DONE)
        status = "ok"
        return 0
    except TaskInterrupted:
        elapsed = time.monotonic() - started_at
        final_text = append_duration_footer(
            INTERRUPT_REPLY,
            elapsed,
            task_kind=task_kind,
        )
        _append_assistant(final_text)
        _emit(store, run_id, {"type": "done", "text": final_text})
        store.mark_status(run_id, RUN_STATUS_INTERRUPTED)
        status = "interrupted"
        return 0
    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - started_at
        err_msg = str(exc)
        logger.exception("Web chat worker failed run=%s session=%s", run_id, session_id)
        final_text = append_duration_footer(
            f"⚠️ {err_msg}\n\n{RETRY_HINT}",
            elapsed,
            task_kind=task_kind,
        )
        _append_assistant(final_text)
        _emit(
            store,
            run_id,
            {"type": "error", "message": err_msg, "text": final_text},
        )
        store.mark_status(run_id, RUN_STATUS_ERROR)
        return 1
    finally:
        clear_batch_progress(user_key)
        session_ctrl.end()
        if status != "interrupted":
            get_duration_store().record(
                task_kind,
                time.monotonic() - started_at,
                status=status,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Web Agent run worker")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return _run_once(args.run_id.strip())


if __name__ == "__main__":
    raise SystemExit(main())
