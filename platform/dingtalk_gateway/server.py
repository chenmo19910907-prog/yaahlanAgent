#!/usr/bin/env python3
"""Step 8：钉钉 @机器人 → Cursor Agent → 回群。"""

from __future__ import annotations

import logging
import sys
import threading
import time
from queue import Queue

import dingtalk_stream
from dingtalk_stream import AckMessage

from bridge_manager import init_sdk_bridge
from command_router import try_route
from conversation_store import ConversationStore
from user_agent_pool import UserAgentPool
from cursor_runner import DEFAULT_TIMEOUT_S, repo_cwd, run_agent_prompt, truncate_for_dingtalk
from code_modify_permission import (
    code_modify_denial_message,
    is_code_modify_allowed,
    looks_like_code_modify_request,
)
from progress_message import build_heartbeat_message
from dingtalk_media import download_message_images
from env_loader import load_env_local, require_env
from moa_health import probe_moa_cookie
from dingtalk_group_file import send_group_file
from export_delivery import deliver_reply, is_view_all_follow_up
from inbound_message import InboundMessage, parse_inbound_message
from interrupt import is_interrupt_command
from replay import is_replay_command
from quoted_reply import quote_text_from_inbound, reply_quoted
from reply_formatter import format_exception, format_group_reply
from task_session import TaskInterrupted, TaskSession
from testcase_auto_export import (
    export_generated_testcases_safe,
    format_testcase_export_message,
)

logger = logging.getLogger("dingtalk-gateway")
HEARTBEAT_INTERVAL_S = 55


class GatewayBotHandler(dingtalk_stream.ChatbotHandler):
    def __init__(
        self,
        task_queue: Queue[tuple[dingtalk_stream.ChatbotMessage, InboundMessage]],
        session: TaskSession,
        store: ConversationStore,
    ) -> None:
        super().__init__()
        self._task_queue = task_queue
        self._session = session
        self._store = store

    def _user_session_key(self, incoming: dingtalk_stream.ChatbotMessage) -> str:
        return UserAgentPool.user_key(
            conversation_id=incoming.conversation_id,
            sender_id=incoming.sender_id,
            sender_staff_id=incoming.sender_staff_id,
            conversation_type=incoming.conversation_type,
        )

    def _store_lookup_kwargs(self, incoming: dingtalk_stream.ChatbotMessage) -> dict[str, str | None]:
        return {
            "sender_id": incoming.sender_id,
            "sender_staff_id": incoming.sender_staff_id,
            "conversation_type": incoming.conversation_type,
        }

    def _reply(
        self,
        body: str,
        incoming: dingtalk_stream.ChatbotMessage,
        inbound: InboundMessage | None = None,
        *,
        quote: bool = True,
    ) -> None:
        if quote:
            reply_quoted(self, body, incoming, quote_text=quote_text_from_inbound(inbound))
        else:
            self.reply_text(body, incoming)

    async def process(self, callback: dingtalk_stream.CallbackMessage):
        incoming = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
        inbound = parse_inbound_message(incoming)
        conv_id = self._user_session_key(incoming)
        store_kwargs = self._store_lookup_kwargs(incoming)

        if is_interrupt_command(inbound.text):
            cancel_result = self._session.request_cancel(conv_id)
            if cancel_result is True:
                self._reply("✅ 已中断本群正在执行的操作。", incoming, inbound)
            elif cancel_result is False:
                self._reply(
                    "当前正在执行其它会话的任务，本群无法中断。\n"
                    f"进行中：{self._session.current_prompt()[:60]}…",
                    incoming,
                    inbound,
                )
            else:
                self._reply("当前没有正在执行的任务。", incoming, inbound)
            return AckMessage.STATUS_OK, "OK"

        if is_replay_command(inbound.text):
            last_prompt = self._store.get_last(incoming.conversation_id, **store_kwargs)
            if not last_prompt:
                self._reply("您暂无上次任务，无法重新执行。", incoming, inbound)
                return AckMessage.STATUS_OK, "OK"
            inbound = InboundMessage(text=last_prompt)
            self._reply(f"已收到（重新执行：{last_prompt[:50]}…），执行中…", incoming, inbound)
            self._task_queue.put((incoming, inbound))
            return AckMessage.STATUS_OK, "OK"

        if inbound.is_empty:
            self._reply(
                "请输入文字、图片或图文链接。常用：\n"
                "• `帮助` — 能力说明\n"
                "• `MOA检查` — 测试 MOA 是否可用\n"
                "• `中断操作` / `重新执行`",
                incoming,
                inbound,
            )
            return AckMessage.STATUS_OK, "OK"

        pending = self._task_queue.qsize()
        busy = self._session.is_busy()
        if busy or pending > 0:
            ahead = pending + (1 if busy else 0)
            self._reply(
                f"已收到（{inbound.summary_label()}），排队中（前面约 {ahead} 个）…\n"
                "本群任务执行中可发「中断操作」打断。",
                incoming,
                inbound,
            )
        else:
            self._reply(f"已收到（{inbound.summary_label()}），执行中…", incoming, inbound)
        self._task_queue.put((incoming, inbound))
        return AckMessage.STATUS_OK, "OK"


def _start_heartbeat(
    handler: GatewayBotHandler,
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


def worker_loop(
    task_queue: Queue[tuple[dingtalk_stream.ChatbotMessage, InboundMessage]],
    handler: GatewayBotHandler,
    session: TaskSession,
    store: ConversationStore,
) -> None:
    while True:
        incoming, inbound = task_queue.get()
        prompt = inbound.prompt_text()
        conv_id = handler._user_session_key(incoming)
        store_kwargs = handler._store_lookup_kwargs(incoming)
        user_key = conv_id
        sender_name = incoming.sender_nick or incoming.sender_staff_id or incoming.sender_id or ""
        started = time.monotonic()
        started_wall = time.time()
        session.begin(prompt, conversation_id=conv_id, budget_s=DEFAULT_TIMEOUT_S)
        heartbeat_stop = _start_heartbeat(handler, incoming, session, conv_id)
        status = "error"
        try:
            logger.info(
                "开始处理 conv=%s user=%s msg=%s text=%s",
                conv_id,
                sender_name,
                incoming.message_id,
                prompt[:120],
            )
            session.check_cancelled()

            if is_view_all_follow_up(prompt):
                cached = store.get_last_full_reply(
                    incoming.conversation_id,
                    **store_kwargs,
                )
                if cached:
                    delivery = deliver_reply(cached, prompt)
                    handler._reply(delivery.message, incoming, inbound)
                    store.save(incoming.conversation_id, prompt, **store_kwargs)
                    status = "ok"
                    continue

            image_paths = []
            if inbound.image_download_codes:
                image_paths = download_message_images(
                    handler,
                    inbound.image_download_codes,
                    session_id=incoming.message_id or "unknown",
                )
                session.check_cancelled()

            routed = try_route(prompt, session=session)
            if routed.handled:
                raw_result = routed.output
                logger.info("快捷指令完成 conv=%s", conv_id)
                result = format_group_reply(raw_result, prompt=prompt, source="route")
                store.save_full_reply(incoming.conversation_id, result, **store_kwargs)
                delivery = deliver_reply(result, prompt)
                handler._reply(delivery.message, incoming, inbound)
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
                code_allowed = is_code_modify_allowed(
                    sender_staff_id=incoming.sender_staff_id,
                    sender_id=incoming.sender_id,
                )
                if looks_like_code_modify_request(prompt) and not code_allowed:
                    logger.warning(
                        "代码修改权限拒绝 conv=%s staff=%s sender=%s prompt=%s",
                        conv_id,
                        incoming.sender_staff_id,
                        incoming.sender_id,
                        prompt[:120],
                    )
                    handler._reply(code_modify_denial_message(), incoming, inbound)
                    store.save(incoming.conversation_id, prompt, **store_kwargs)
                    status = "denied"
                    continue

                raw_result = run_agent_prompt(
                    prompt,
                    image_paths=image_paths,
                    links=inbound.links,
                    session=session,
                    user_key=user_key,
                    sender_name=sender_name,
                    allow_code_modify=code_allowed,
                )
                result = format_group_reply(raw_result, prompt=prompt, source="agent")
                store.save_full_reply(incoming.conversation_id, result, **store_kwargs)
                delivery = deliver_reply(result, prompt)
                reply_message = delivery.message
                tc_items = export_generated_testcases_safe(
                    repo_root=repo_cwd(),
                    prompt=prompt,
                    since_wall_ts=started_wall,
                )
                if tc_items:
                    tc_message = format_testcase_export_message(tc_items)
                    if tc_message:
                        reply_message = (
                            f"{reply_message}\n\n{tc_message}"
                            if reply_message.strip()
                            else tc_message
                        )
                handler._reply(truncate_for_dingtalk(reply_message), incoming, inbound)
                if delivery.exported:
                    logger.info("已导出 %s url=%s", delivery.local_path, delivery.file_url)
                for item in tc_items:
                    if item.url:
                        logger.info("测试用例已同步 %s url=%s", item.name, item.url)
            store.save(incoming.conversation_id, prompt, **store_kwargs)
            status = "ok"
        except TaskInterrupted:
            status = "interrupted"
            logger.info("任务已中断 conv=%s prompt=%s", conv_id, prompt[:120])
            handler._reply("⚠️ 任务已被中断。", incoming, inbound)
            store.save(incoming.conversation_id, prompt, **store_kwargs)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            logger.exception("任务失败 conv=%s", conv_id)
            handler._reply(format_exception(exc), incoming, inbound)
            store.save(incoming.conversation_id, prompt, **store_kwargs)
        finally:
            heartbeat_stop.set()
            session.end()
            task_queue.task_done()
            elapsed = time.monotonic() - started
            logger.info(
                "任务结束 conv=%s msg=%s status=%s duration=%.1fs",
                conv_id,
                incoming.message_id,
                status,
                elapsed,
            )


def main() -> int:
    load_env_local()
    try:
        require_env("CURSOR_API_KEY")
        require_env("DINGTALK_CLIENT_ID")
        require_env("DINGTALK_CLIENT_SECRET")
    except RuntimeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_sdk_bridge(repo_cwd())

    moa_ok, moa_detail = probe_moa_cookie()
    if moa_ok:
        logger.info("启动探活 MOA: %s", moa_detail)
    else:
        logger.warning("启动探活 MOA 异常: %s", moa_detail)

    task_queue: Queue[tuple[dingtalk_stream.ChatbotMessage, InboundMessage]] = Queue()
    session = TaskSession()
    store = ConversationStore()
    handler = GatewayBotHandler(task_queue, session, store)
    threading.Thread(
        target=worker_loop,
        args=(task_queue, handler, session, store),
        daemon=True,
        name="gateway-worker",
    ).start()

    credential = dingtalk_stream.Credential(
        require_env("DINGTALK_CLIENT_ID"),
        require_env("DINGTALK_CLIENT_SECRET"),
    )
    client = dingtalk_stream.DingTalkStreamClient(credential)
    client.register_callback_handler(
        dingtalk_stream.chatbot.ChatbotMessage.TOPIC,
        handler,
    )
    logger.info("Yaahlan 钉钉网关已启动（每用户独立 Agent 窗口/帮助/重试/MOA检查/中断/排队）")
    client.start_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
