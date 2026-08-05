"""Web Agent 任务执行：HTTP 进程内线程运行（复用 Bridge/Agent 池，避免子进程冷启动）。"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from batch_progress import clear_batch_progress
from cursor_runner import DEFAULT_TIMEOUT_S
from duration_history import classify_task_kind, get_duration_store
from external_agent_progress import USER_KEY_ENV, clear_external_agent_progress
from task_session import TaskInterrupted, TaskSession

from chat_runner import run_web_chat
from web_file_store import consume_pending_outputs
from web_prompt import finalize_web_reply_text
from web_run_store import (
    RUN_STATUS_DONE,
    RUN_STATUS_ERROR,
    RUN_STATUS_INTERRUPTED,
    RUN_STATUS_RUNNING,
    get_run_store,
)
from web_session_store import get_session_store

logger = logging.getLogger("web-agent")

INTERRUPT_REPLY = "⚠️ 任务已中断。"
RETRY_HINT = "💡 原消息已回填到输入框，请检查后重试。"

_RUN_THREADS: dict[str, threading.Thread] = {}
_RUN_THREADS_LOCK = threading.Lock()


class FileBackedTaskSession(TaskSession):
    """从落盘 cancel 标记感知用户中断。"""

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self._run_id = run_id
        self._store = get_run_store()

    def check_cancelled(self) -> None:
        if self._store.is_cancel_requested(self._run_id):
            self.arm_cancel()
        super().check_cancelled()


def is_run_thread_alive(run_id: str) -> bool:
    rid = (run_id or "").strip()
    if not rid:
        return False
    with _RUN_THREADS_LOCK:
        thread = _RUN_THREADS.get(rid)
    return thread is not None and thread.is_alive()


def _emit(store: Any, run_id: str, event: dict[str, Any]) -> None:
    store.append_event(run_id, event)


def _maybe_push_result_to_dingtalk(meta: Any, text: str, *, success: bool) -> dict[str, Any] | None:
    if not success or not meta.push_result_to_dingtalk:
        return None
    staff_id = (meta.push_dingtalk_staff_id or meta.author_id or "").strip()
    if not staff_id:
        return {"ok": False, "error": "缺少钉钉用户标识"}
    try:
        from web_dingtalk_push import push_web_result_to_dingtalk  # noqa: WPS433

        push_web_result_to_dingtalk(staff_id, text)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "钉钉推送失败 run=%s staff=%s: %s",
            meta.run_id,
            staff_id[:12],
            exc,
        )
        return {"ok": False, "error": str(exc)}


def execute_web_run(run_id: str) -> int:
    """执行单次 Web chat run（可在子进程或 HTTP 服务线程内调用）。"""
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
    if user_key:
        os.environ[USER_KEY_ENV] = user_key
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

    def on_render(markdown: str, process: dict[str, Any] | None = None) -> None:
        nonlocal last_markdown
        last_markdown = markdown
        event: dict[str, Any] = {"type": "delta", "markdown": markdown}
        if isinstance(process, dict):
            event["process"] = process
        _emit(store, run_id, event)

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
            reply_mode=meta.reply_mode or None,
        )
        elapsed = time.monotonic() - started_at
        body = final or last_markdown
        final_text = finalize_web_reply_text(
            body,
            elapsed,
            task_kind=task_kind,
            prompt=meta.message,
            reply_mode=meta.reply_mode,
        )
        _append_assistant(final_text)
        dingtalk_push = _maybe_push_result_to_dingtalk(meta, final_text, success=True)
        done_event: dict[str, Any] = {"type": "done", "text": final_text}
        if dingtalk_push is not None:
            done_event["dingtalk_push"] = dingtalk_push
        _emit(store, run_id, done_event)
        store.mark_status(run_id, RUN_STATUS_DONE)
        status = "ok"
        return 0
    except TaskInterrupted:
        elapsed = time.monotonic() - started_at
        final_text = finalize_web_reply_text(
            INTERRUPT_REPLY,
            elapsed,
            task_kind=task_kind,
            prompt=meta.message,
            reply_mode=meta.reply_mode,
        )
        _append_assistant(final_text)
        _emit(store, run_id, {"type": "done", "text": final_text})
        store.mark_status(run_id, RUN_STATUS_INTERRUPTED)
        status = "interrupted"
        return 0
    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - started_at
        err_msg = str(exc)
        logger.exception("Web chat run failed run=%s session=%s", run_id, session_id)
        final_text = finalize_web_reply_text(
            f"⚠️ {err_msg}\n\n{RETRY_HINT}",
            elapsed,
            task_kind=task_kind,
            prompt=meta.message,
            reply_mode=meta.reply_mode,
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
        clear_external_agent_progress(user_key)
        os.environ.pop(USER_KEY_ENV, None)
        session_ctrl.end()
        if status != "interrupted":
            get_duration_store().record(
                task_kind,
                time.monotonic() - started_at,
                status=status,
            )


def start_run_in_background(run_id: str) -> int:
    """在 HTTP 服务进程内后台线程执行 run，复用已预热的 Bridge/Agent。"""
    rid = (run_id or "").strip()
    if not rid:
        raise ValueError("run_id 不能为空")
    if is_run_thread_alive(rid):
        logger.info("run %s 已在执行中，跳过重复启动", rid)
        return os.getpid()

    store = get_run_store()

    def _target() -> None:
        try:
            execute_web_run(rid)
        finally:
            with _RUN_THREADS_LOCK:
                _RUN_THREADS.pop(rid, None)

    thread = threading.Thread(
        target=_target,
        daemon=True,
        name=f"web-run-{rid}",
    )
    with _RUN_THREADS_LOCK:
        _RUN_THREADS[rid] = thread
    store.set_worker_pid(rid, os.getpid())
    thread.start()
    logger.info("start in-process run=%s pid=%s", rid, os.getpid())
    return os.getpid()


def init_agent_runtime() -> None:
    """HTTP 服务启动时预热 Bridge 与 Agent 池。"""
    from chat_runner import ensure_bridge

    ensure_bridge()
    logger.info("Web Agent 运行时已预热（Bridge + Agent 池）")
