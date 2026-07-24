"""单条入站任务的处理逻辑（fast / agent 队列共用）。"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import dingtalk_stream

from adb_execution_guard import adb_execution_denial_message, looks_like_adb_execution_request
from env_check_guard import (
    env_check_denial_message,
    guard_env_check_agent_reply,
    looks_like_env_check_request,
)
from agent_stream_card import (
    is_agent_streaming_enabled,
    try_create_agent_stream_card,
)
from progress_message import (
    build_streaming_ack,
    build_streaming_card_title,
    build_streaming_prompt_quote,
)
from batch_progress import (
    PUSH_POLL_INTERVAL_S,
    build_batch_progress_message,
    clear_batch_progress,
    is_batch_progress_active,
    read_batch_progress,
    should_push_batch_progress,
)
from batch_result import choose_final_reply_source, clear_batch_result, pop_batch_attachment, pop_batch_result
from command_hints import suggest_command_hint
from command_router import try_route
from code_modify_guard import guard_readonly_agent_reply
from code_modify_permission import (
    code_modify_denial_message,
    is_code_modify_allowed,
    looks_like_code_modify_request,
)
from code_modify_permission import (
    allow_moa_registry_in_readonly,
    is_code_modify_allowed,
)
from cursor_runner import (
    DEFAULT_TIMEOUT_S,
    repo_cwd,
    run_agent_prompt,
    run_agent_prompt_streaming,
    truncate_for_dingtalk,
)
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
from progress_message import (
    HEARTBEAT_MAX_COUNT,
    append_duration_footer,
    build_heartbeat_message,
    compute_heartbeat_schedule,
    resolve_task_estimate_seconds,
)
from queue_persist import get_queue_persist
from reply_formatter import format_exception, format_group_reply
from route_patterns import is_web_login_request, normalize_fuzzy_fast_command, normalize_report_prompt
from task_session import TaskInterrupted, TaskSession
from testcase_auto_export import (
    export_generated_testcases_safe,
    format_testcase_export_message,
)
from user_agent_pool import get_user_agent_pool
from web_agent_sync import sync_exchange_to_web_agent
from web_login_route import handle_web_login_request

logger = logging.getLogger("dingtalk-gateway")

# 流式卡片内批量进度轮询间隔：每秒刷新，展示最新 N/M（卡片内更新不刷屏）
STREAMING_BATCH_POLL_INTERVAL_S = 1.0


def _reply_final(
    handler: Any,
    incoming: dingtalk_stream.ChatbotMessage,
    inbound: InboundMessage | None,
    message: str,
    *,
    started: float,
    task_kind: str,
    quote: bool = True,
    user_key: str = "",
    user_prompt: str = "",
    sender_name: str = "",
    sender_staff_id: str = "",
) -> None:
    elapsed = time.monotonic() - started
    body = append_duration_footer(message, elapsed, task_kind=task_kind)
    handler._reply(body, incoming, inbound, quote=quote)
    if user_key and user_prompt:
        sync_exchange_to_web_agent(
            user_key,
            user_prompt,
            body,
            sender_name=sender_name,
            sender_staff_id=sender_staff_id,
        )


def _send_batch_attachment_if_any(
    handler: Any,
    incoming: dingtalk_stream.ChatbotMessage,
    inbound: InboundMessage | None,
    user_key: str,
) -> None:
    attachment = pop_batch_attachment(user_key)
    if attachment is None:
        return
    try:
        send_group_file(
            handler,
            incoming,
            attachment,
            display_name=attachment.name,
        )
    except Exception as file_exc:  # noqa: BLE001
        logger.exception("发送批量附件失败")
        handler._reply(
            f"⚠️ 摘要已发送，但附件 {attachment.name} 上传失败：{file_exc}",
            incoming,
            inbound,
        )


def _heartbeat_estimate_seconds(task_kind: str) -> float | None:
    return resolve_task_estimate_seconds(task_kind)


def _start_heartbeat(
    handler: Any,
    incoming: dingtalk_stream.ChatbotMessage,
    session: TaskSession,
    conversation_id: str,
    *,
    lane: str,
    task_kind: str,
    user_key: str = "",
) -> threading.Event:
    stop = threading.Event()
    if lane == "fast":
        return stop

    initial_delay, interval = compute_heartbeat_schedule(task_kind)

    def loop() -> None:
        if stop.wait(initial_delay):
            return
        sent = 0
        while sent < HEARTBEAT_MAX_COUNT:
            if not session.is_busy():
                return
            if session.busy_conversation_id() != conversation_id:
                return
            if user_key and is_batch_progress_active(user_key):
                if stop.wait(interval):
                    return
                continue
            try:
                estimate = _heartbeat_estimate_seconds(task_kind)
                handler._reply(
                    build_heartbeat_message(session, estimate_s=estimate),
                    incoming,
                    quote=False,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("心跳回复失败: %s", exc)
            sent += 1
            if sent >= HEARTBEAT_MAX_COUNT or stop.wait(interval):
                return

    threading.Thread(target=loop, daemon=True, name="gateway-heartbeat").start()
    return stop


def _start_streaming_batch_progress_watcher(
    stream_card: Any,
    session: TaskSession,
    user_key: str,
    *,
    lane: str,
) -> threading.Event:
    """每秒轮询 batch_progress，刷新流式卡片内的 N/M 进度行（卡片内更新无需节流）。"""
    stop = threading.Event()
    if lane == "fast" or not user_key or stream_card is None:
        return stop

    def loop() -> None:
        while not stop.wait(STREAMING_BATCH_POLL_INTERVAL_S):
            if not session.is_busy():
                return
            if session.busy_conversation_id() != user_key:
                return
            state = read_batch_progress(user_key)
            if state is None:
                try:
                    stream_card.clear_batch_progress()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("流式卡片清理批量进度失败: %s", exc)
                continue
            try:
                stream_card.set_batch_progress(build_batch_progress_message(state))
            except Exception as exc:  # noqa: BLE001
                logger.warning("流式卡片批量进度更新失败: %s", exc)
            if state.current >= state.total:
                return

    threading.Thread(
        target=loop,
        daemon=True,
        name="gateway-streaming-batch-progress",
    ).start()
    return stop


def _start_batch_progress_watcher(
    handler: Any,
    incoming: dingtalk_stream.ChatbotMessage,
    inbound: InboundMessage | None,
    session: TaskSession,
    user_key: str,
    *,
    lane: str,
) -> threading.Event:
    """轮询 batch_progress 文件，向群内推送 N/M 进度。"""
    stop = threading.Event()
    if lane == "fast" or not user_key:
        return stop

    def loop() -> None:
        last_pushed = 0
        last_push_at = 0.0
        while not stop.wait(PUSH_POLL_INTERVAL_S):
            if not session.is_busy():
                return
            if session.busy_conversation_id() != user_key:
                return
            state = read_batch_progress(user_key)
            if state is None:
                continue
            now = time.monotonic()
            if not should_push_batch_progress(
                state,
                last_pushed_current=last_pushed,
                last_push_at=last_push_at,
                now=now,
            ):
                continue
            try:
                handler._reply(
                    build_batch_progress_message(state),
                    incoming,
                    inbound,
                    quote=False,
                )
                last_pushed = state.current
                last_push_at = now
            except Exception as exc:  # noqa: BLE001
                logger.warning("批量进度推送失败: %s", exc)
            if state.current >= state.total:
                return

    threading.Thread(
        target=loop,
        daemon=True,
        name="gateway-batch-progress",
    ).start()
    return stop


def _schedule_testcase_export_followup(
    handler: Any,
    incoming: dingtalk_stream.ChatbotMessage,
    inbound: InboundMessage | None,
    *,
    prompt: str,
    started_wall: float,
) -> None:
    """后台同步测试用例到钉钉，完成后单独发一条链接消息。"""

    def worker() -> None:
        try:
            tc_items = export_generated_testcases_safe(
                repo_root=repo_cwd(),
                prompt=prompt,
                since_wall_ts=started_wall,
            )
            if not tc_items:
                return
            tc_message = format_testcase_export_message(tc_items)
            if not tc_message:
                return
            handler._reply(
                truncate_for_dingtalk(tc_message),
                incoming,
                inbound,
                quote=False,
            )
            for item in tc_items:
                if item.url:
                    logger.info("测试用例已同步 %s url=%s", item.name, item.url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("后台用例导出失败: %s", exc)

    threading.Thread(
        target=worker,
        daemon=True,
        name="gateway-tc-export",
    ).start()


def process_inbound_task(
    handler: Any,
    incoming: dingtalk_stream.ChatbotMessage,
    inbound: InboundMessage,
    *,
    session: TaskSession,
    user_key: str,
    lane: str = "agent",
    preassigned_card: Any = None,
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
    else:
        fuzzy = normalize_fuzzy_fast_command(prompt)
        if fuzzy:
            prompt = fuzzy
            inbound = InboundMessage(
                text=fuzzy,
                image_download_codes=inbound.image_download_codes,
                links=inbound.links,
            )

    sender_name = incoming.sender_nick or incoming.sender_staff_id or incoming.sender_id or ""
    sender_staff_id = incoming.sender_staff_id or incoming.sender_id or ""
    task_kind = classify_task_kind(prompt)
    task_estimate_s = resolve_task_estimate_seconds(task_kind, prompt=prompt)
    started = time.monotonic()
    started_wall = time.time()
    use_streaming = lane == "agent" and is_agent_streaming_enabled()
    if preassigned_card is not None:
        # 入队时已预投放卡片，复用同一张（禁止再 reply 新卡片）
        stream_card = preassigned_card
        use_streaming = True
        try:
            if stream_card.is_active:
                stream_card.begin_running(
                    build_streaming_ack(inbound.summary_label(), prompt=prompt),
                    estimate_seconds=task_estimate_s,
                )
            else:
                stream_card.start(
                    "⏳ Agent 启动中…",
                    header=build_streaming_ack(inbound.summary_label(), prompt=prompt),
                    persistent_header=build_streaming_prompt_quote(prompt),
                    card_title=build_streaming_card_title(prompt),
                    estimate_seconds=task_estimate_s,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("流式卡片转入执行态失败，回退文本回复: %s", exc)
            stream_card = None
            use_streaming = False
    else:
        stream_card = try_create_agent_stream_card(handler, incoming) if use_streaming else None
        if use_streaming and stream_card is None:
            use_streaming = False
        elif stream_card is not None:
            try:
                stream_card.start(
                    "⏳ Agent 启动中…",
                    header=build_streaming_ack(inbound.summary_label(), prompt=prompt),
                    persistent_header=build_streaming_prompt_quote(prompt),
                    card_title=build_streaming_card_title(prompt),
                    estimate_seconds=task_estimate_s,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("流式卡片启动失败，回退文本回复: %s", exc)
                stream_card = None
                use_streaming = False
    session.begin(prompt, conversation_id=user_key, budget_s=DEFAULT_TIMEOUT_S)
    clear_batch_progress(user_key)
    clear_batch_result(user_key)
    if use_streaming:
        heartbeat_stop = threading.Event()
        batch_progress_stop = (
            _start_streaming_batch_progress_watcher(
                stream_card,
                session,
                user_key,
                lane=lane,
            )
            if stream_card is not None
            else threading.Event()
        )
    else:
        heartbeat_stop = _start_heartbeat(
            handler,
            incoming,
            session,
            user_key,
            lane=lane,
            task_kind=task_kind,
            user_key=user_key,
        )
        batch_progress_stop = _start_batch_progress_watcher(
            handler,
            incoming,
            inbound,
            session,
            user_key,
            lane=lane,
        )
    status = "error"
    code_modify_session = False
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
                    user_key=user_key,
                    user_prompt=prompt,
                    sender_name=sender_name,
                    sender_staff_id=sender_staff_id,
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
                user_key=user_key,
                user_prompt=prompt,
                sender_name=sender_name,
                sender_staff_id=sender_staff_id,
            )
            store.save(incoming.conversation_id, prompt, **store_kwargs)
            return "no_cache"

        if looks_like_env_check_request(prompt):
            logger.info("环境检查已取消 conv=%s", user_key)
            _reply_final(
                handler,
                incoming,
                inbound,
                env_check_denial_message(),
                started=started,
                task_kind=classify_task_kind(prompt),
                user_key=user_key,
                user_prompt=prompt,
                sender_name=sender_name,
                sender_staff_id=sender_staff_id,
            )
            store.save(incoming.conversation_id, prompt, **store_kwargs)
            return "denied_env_check"

        if is_web_login_request(prompt):
            task_kind = classify_task_kind(prompt, route_kind="web_login")
            group_reply, _dm_ok = handle_web_login_request(
                sender_staff_id=sender_staff_id,
                sender_name=sender_name,
                conversation_type=incoming.conversation_type,
                client=getattr(handler, "dingtalk_client", None),
            )
            _reply_final(
                handler,
                incoming,
                inbound,
                group_reply,
                started=started,
                task_kind=task_kind,
                user_key=user_key,
                user_prompt=prompt,
                sender_name=sender_name,
                sender_staff_id=sender_staff_id,
            )
            return "ok"

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
                user_key=user_key,
                user_prompt=prompt,
                sender_name=sender_name,
                sender_staff_id=sender_staff_id,
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
            _send_batch_attachment_if_any(handler, incoming, inbound, user_key)
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
                    user_key=user_key,
                    user_prompt=prompt,
                    sender_name=sender_name,
                    sender_staff_id=sender_staff_id,
                )
                store.save(incoming.conversation_id, prompt, **store_kwargs)
                return "hint"

            code_allowed = is_code_modify_allowed(
                sender_staff_id=incoming.sender_staff_id,
                sender_id=incoming.sender_id,
            )
            allow_moa_registry = allow_moa_registry_in_readonly(
                code_modify_allowed=code_allowed,
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
                    user_key=user_key,
                    user_prompt=prompt,
                    sender_name=sender_name,
                    sender_staff_id=sender_staff_id,
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
                    user_key=user_key,
                    user_prompt=prompt,
                    sender_name=sender_name,
                    sender_staff_id=sender_staff_id,
                )
                store.save(incoming.conversation_id, prompt, **store_kwargs)
                return "adb_denied"

            session.set_phase("agent")
            if use_streaming and stream_card is not None:
                raw_result = run_agent_prompt_streaming(
                    prompt,
                    on_render=stream_card.push,
                    image_paths=image_paths,
                    links=inbound.links,
                    session=session,
                    user_key=user_key,
                    sender_name=sender_name,
                    allow_code_modify=code_allowed,
                    allow_moa_registry=allow_moa_registry,
                )
            else:
                raw_result = run_agent_prompt(
                    prompt,
                    image_paths=image_paths,
                    links=inbound.links,
                    session=session,
                    user_key=user_key,
                    sender_name=sender_name,
                    allow_code_modify=code_allowed,
                    allow_moa_registry=allow_moa_registry,
                )
            session.check_cancelled()
            raw_result = guard_readonly_agent_reply(
                raw_result,
                allow_code_modify=code_allowed,
                allow_moa_registry=allow_moa_registry,
            )
            raw_result = guard_env_check_agent_reply(raw_result, prompt=prompt)
            session.check_cancelled()
            agent_formatted = format_group_reply(
                raw_result,
                prompt=prompt,
                source="agent",
                preserve_markdown=stream_card is not None,
            )
            batch_result = pop_batch_result(user_key)
            final_body, final_source = choose_final_reply_source(
                agent_formatted=agent_formatted,
                batch_result=batch_result,
            )
            if final_source == "batch":
                logger.info("批量任务使用 --result-text 作为最终群消息 conv=%s", user_key)
            store.save_full_reply(incoming.conversation_id, final_body, **store_kwargs)
            session.set_phase("reply")
            session.check_cancelled()
            delivery = deliver_reply(final_body, prompt)
            reply_message = delivery.message
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
            reply_text = truncate_for_dingtalk(reply_message)
            if stream_card is not None:
                # 流式卡片仅收尾为完成态；最终结果另发新消息（@提问人 + 提问引用 + Markdown）
                stream_card.finish_status("✅ 执行完成，结果见下方消息 ↓")
            _reply_final(
                handler,
                incoming,
                inbound,
                reply_text,
                started=started,
                task_kind=task_kind,
                user_key=user_key,
                user_prompt=prompt,
                sender_name=sender_name,
                sender_staff_id=sender_staff_id,
            )
            _send_batch_attachment_if_any(handler, incoming, inbound, user_key)
            if delivery.exported:
                logger.info("已导出 %s url=%s", delivery.local_path, delivery.file_url)
            _schedule_testcase_export_followup(
                handler,
                incoming,
                inbound,
                prompt=prompt,
                started_wall=started_wall,
            )

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
        interrupt_body = "⚠️ 你的任务已被中断。"
        if stream_card is not None:
            stream_card.finish(interrupt_body)
        else:
            handler._reply(interrupt_body, incoming, inbound)
        if user_key and prompt:
            sync_exchange_to_web_agent(
                user_key,
                prompt,
                interrupt_body,
                sender_name=sender_name,
                sender_staff_id=sender_staff_id,
            )
        store.save(incoming.conversation_id, prompt, **store_kwargs)
        get_user_agent_pool().invalidate(user_key)
    except Exception as exc:  # noqa: BLE001
        status = "error"
        logger.exception("任务失败 conv=%s", user_key)
        error_body = format_exception(exc)
        error_with_footer = append_duration_footer(
            error_body,
            time.monotonic() - started,
            task_kind=task_kind,
        )
        if stream_card is not None:
            stream_card.fail(error_with_footer)
        else:
            _reply_final(
                handler,
                incoming,
                inbound,
                error_body,
                started=started,
                task_kind=task_kind,
                user_key=user_key,
                user_prompt=prompt,
                sender_name=sender_name,
                sender_staff_id=sender_staff_id,
            )
        if user_key and prompt and stream_card is not None:
            sync_exchange_to_web_agent(
                user_key,
                prompt,
                error_with_footer,
                sender_name=sender_name,
                sender_staff_id=sender_staff_id,
            )
        store.save(incoming.conversation_id, prompt, **store_kwargs)
    finally:
        heartbeat_stop.set()
        batch_progress_stop.set()
        clear_batch_progress(user_key)
        clear_batch_result(user_key)
        get_user_agent_pool().touch(user_key)
        session.end()
        persist.remove(user_key=user_key, prompt=prompt)
        elapsed = time.monotonic() - started
        if status != "interrupted":
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
