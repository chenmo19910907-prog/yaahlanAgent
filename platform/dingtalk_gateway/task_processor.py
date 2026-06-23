"""单条入站任务的处理逻辑（fast / agent 队列共用）。"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import dingtalk_stream

from adb_execution_guard import adb_execution_denial_message, looks_like_adb_execution_request
from command_hints import suggest_command_hint
from command_router import try_route
from code_modify_guard import guard_readonly_agent_reply
from code_modify_permission import (
    code_modify_denial_message,
    is_code_modify_allowed,
    looks_like_code_modify_request,
)
from cursor_runner import DEFAULT_TIMEOUT_S, repo_cwd, run_agent_prompt, truncate_for_dingtalk
from duration_history import classify_task_kind, get_duration_store
from gateway_restart import (
    format_code_update_restart_note,
    list_gateway_files_changed_since,
    schedule_gateway_restart_after_code_change,
)
from dingtalk_group_file import send_group_file
from dingtalk_media import download_message_images
from export_delivery import deliver_reply, is_view_all_follow_up
from inbound_message import InboundMessage
from log_redact import redact_for_log
from progress_message import append_duration_footer, build_heartbeat_message
from queue_persist import get_queue_persist
from reply_formatter import format_exception, format_group_reply
from route_patterns import normalize_report_prompt
from task_session import TaskInterrupted, TaskSession
from testcase_auto_export import (
    export_generated_testcases_safe,
    format_testcase_export_message,
)
from user_agent_pool import get_user_agent_pool

logger = logging.getLogger("dingtalk-gateway")
HEARTBEAT_INTERVAL_S = 55


def _reply_final(
    handler: Any,
    incoming: dingtalk_stream.ChatbotMessage,
    inbound: InboundMessage | None,
    message: str,
    *,
    started: float,
    task_kind: str,
    quote: bool = True,
) -> None:
    elapsed = time.monotonic() - started
    body = append_duration_footer(message, elapsed, task_kind=task_kind)
    handler._reply(body, incoming, inbound, quote=quote)


def _start_heartbeat(
    handler: Any,
    incoming: dingtalk_stream.ChatbotMessage,
    session: TaskSession,
    conversation_id: str,
) -> threading.Event:
    stop = threading.Event()

    def loop() -> None:
        while not stop.wait(HEARTBEAT_INTERVAL_S):
            if not session.is_busy():
                return
            if session.busy_conversation_id() != conversation_id:
                return
            try:
                handler._reply(build_heartbeat_message(session), incoming, quote=False)
            except Exception as exc:  # noqa: BLE001
                logger.warning("心跳回复失败: %s", exc)

    threading.Thread(target=loop, daemon=True, name="gateway-heartbeat").start()
    return stop


def process_inbound_task(
    handler: Any,
    incoming: dingtalk_stream.ChatbotMessage,
    inbound: InboundMessage,
    *,
    session: TaskSession,
    user_key: str,
    lane: str = "agent",
) -> str:
    """处理一条任务，返回 status 字符串。"""
    store = handler._store
    store_kwargs = handler._store_lookup_kwargs(incoming)
    prompt = inbound.prompt_text()
    normalized = normalize_report_prompt(prompt)
    if normalized:
        prompt = normalized
        inbound = InboundMessage(
            text=normalized,
            image_download_codes=inbound.image_download_codes,
            links=inbound.links,
        )

    sender_name = incoming.sender_nick or incoming.sender_staff_id or incoming.sender_id or ""
    started = time.monotonic()
    started_wall = time.time()
    session.begin(prompt, conversation_id=user_key, budget_s=DEFAULT_TIMEOUT_S)
    heartbeat_stop = _start_heartbeat(handler, incoming, session, user_key)
    status = "error"
    code_modify_session = False
    task_kind = classify_task_kind(prompt)
    persist = get_queue_persist()
    try:
        logger.info(
            "开始处理 lane=%s conv=%s user=%s msg=%s text=%s",
            lane,
            user_key,
            sender_name,
            incoming.message_id,
            redact_for_log(prompt),
        )
        session.check_cancelled()

        if is_view_all_follow_up(prompt):
            task_kind = classify_task_kind(prompt)
            cached = store.get_last_full_reply(incoming.conversation_id, **store_kwargs)
            if cached:
                delivery = deliver_reply(cached, prompt)
                _reply_final(
                    handler,
                    incoming,
                    inbound,
                    delivery.message,
                    started=started,
                    task_kind=task_kind,
                )
                store.save(incoming.conversation_id, prompt, **store_kwargs)
                return "ok"
            _reply_final(
                handler,
                incoming,
                inbound,
                "暂无完整结果缓存。\n"
                "请先 @机器人 执行一次查询任务，再发「查看全部数据」。",
                started=started,
                task_kind=task_kind,
            )
            store.save(incoming.conversation_id, prompt, **store_kwargs)
            return "no_cache"

        image_paths = []
        if inbound.image_download_codes:
            session.set_phase("prepare")
            image_paths = download_message_images(
                handler,
                inbound.image_download_codes,
                session_id=incoming.message_id or "unknown",
                session=session,
            )
            session.check_cancelled()

        session.set_phase("route")
        routed = try_route(prompt, session=session)
        if routed.handled:
            if routed.task_kind:
                task_kind = classify_task_kind(prompt, route_kind=routed.task_kind)
            raw_result = routed.output
            logger.info("快捷指令完成 conv=%s", user_key)
            result = format_group_reply(raw_result, prompt=prompt, source="route")
            store.save_full_reply(incoming.conversation_id, result, **store_kwargs)
            delivery = deliver_reply(result, prompt)
            _reply_final(
                handler,
                incoming,
                inbound,
                delivery.message,
                started=started,
                task_kind=task_kind,
            )
            for attachment in routed.files:
                try:
                    send_group_file(
                        handler,
                        incoming,
                        attachment,
                        display_name=attachment.name,
                    )
                except Exception as file_exc:  # noqa: BLE001
                    logger.exception("发送报告附件失败")
                    handler._reply(
                        f"⚠️ 报告摘要已发送，但附件上传失败：{file_exc}",
                        incoming,
                        inbound,
                    )
        else:
            hint = suggest_command_hint(prompt)
            if hint:
                _reply_final(
                    handler,
                    incoming,
                    inbound,
                    hint,
                    started=started,
                    task_kind=task_kind,
                )
                store.save(incoming.conversation_id, prompt, **store_kwargs)
                return "hint"

            code_allowed = is_code_modify_allowed(
                sender_staff_id=incoming.sender_staff_id,
                sender_id=incoming.sender_id,
            )
            code_modify_session = code_allowed
            if looks_like_code_modify_request(prompt) and not code_allowed:
                logger.warning(
                    "代码修改权限拒绝 conv=%s staff=%s sender=%s prompt=%s",
                    user_key,
                    incoming.sender_staff_id,
                    incoming.sender_id,
                    redact_for_log(prompt),
                )
                _reply_final(
                    handler,
                    incoming,
                    inbound,
                    code_modify_denial_message(),
                    started=started,
                    task_kind=task_kind,
                )
                store.save(incoming.conversation_id, prompt, **store_kwargs)
                return "denied"

            if looks_like_adb_execution_request(prompt):
                logger.info(
                    "ADB 执行拒绝 conv=%s prompt=%s",
                    user_key,
                    redact_for_log(prompt),
                )
                _reply_final(
                    handler,
                    incoming,
                    inbound,
                    adb_execution_denial_message(),
                    started=started,
                    task_kind=task_kind,
                )
                store.save(incoming.conversation_id, prompt, **store_kwargs)
                return "adb_denied"

            session.set_phase("agent")
            raw_result = run_agent_prompt(
                prompt,
                image_paths=image_paths,
                links=inbound.links,
                session=session,
                user_key=user_key,
                sender_name=sender_name,
                allow_code_modify=code_allowed,
            )
            session.check_cancelled()
            raw_result = guard_readonly_agent_reply(raw_result, allow_code_modify=code_allowed)
            session.check_cancelled()
            result = format_group_reply(raw_result, prompt=prompt, source="agent")
            store.save_full_reply(incoming.conversation_id, result, **store_kwargs)
            session.set_phase("reply")
            session.check_cancelled()
            delivery = deliver_reply(result, prompt)
            reply_message = delivery.message
            session.set_phase("export")
            session.check_cancelled()
            tc_items = export_generated_testcases_safe(
                repo_root=repo_cwd(),
                prompt=prompt,
                since_wall_ts=started_wall,
            )
            session.check_cancelled()
            if tc_items:
                tc_message = format_testcase_export_message(tc_items)
                if tc_message:
                    reply_message = (
                        f"{reply_message}\n\n{tc_message}"
                        if reply_message.strip()
                        else tc_message
                    )
            if code_modify_session:
                session.check_cancelled()
                changed_files = list_gateway_files_changed_since(started_wall)
                if changed_files:
                    schedule_gateway_restart_after_code_change(
                        operator=sender_name,
                        changed_files=changed_files,
                    )
                    reply_message = (
                        f"{reply_message}{format_code_update_restart_note(changed_files)}"
                    )
            session.check_cancelled()
            _reply_final(
                handler,
                incoming,
                inbound,
                truncate_for_dingtalk(reply_message),
                started=started,
                task_kind=task_kind,
            )
            if delivery.exported:
                logger.info("已导出 %s url=%s", delivery.local_path, delivery.file_url)
            for item in tc_items:
                if item.url:
                    logger.info("测试用例已同步 %s url=%s", item.name, item.url)

        store.save(incoming.conversation_id, prompt, **store_kwargs)
        status = "ok"
    except TaskInterrupted:
        status = "interrupted"
        logger.info(
            "任务已中断 lane=%s conv=%s prompt=%s",
            lane,
            user_key,
            redact_for_log(prompt),
        )
        _reply_final(
            handler,
            incoming,
            inbound,
            "⚠️ 你的任务已被中断。",
            started=started,
            task_kind=task_kind,
        )
        store.save(incoming.conversation_id, prompt, **store_kwargs)
        get_user_agent_pool().invalidate(user_key)
    except Exception as exc:  # noqa: BLE001
        status = "error"
        logger.exception("任务失败 conv=%s", user_key)
        _reply_final(
            handler,
            incoming,
            inbound,
            format_exception(exc),
            started=started,
            task_kind=task_kind,
        )
        store.save(incoming.conversation_id, prompt, **store_kwargs)
    finally:
        heartbeat_stop.set()
        get_user_agent_pool().touch(user_key)
        session.end()
        persist.remove(user_key=user_key, prompt=prompt)
        elapsed = time.monotonic() - started
        get_duration_store().record(task_kind, elapsed, status=status)
        logger.info(
            "任务结束 lane=%s conv=%s msg=%s status=%s duration=%.1fs",
            lane,
            user_key,
            incoming.message_id,
            status,
            elapsed,
        )
    return status
