#!/usr/bin/env python3
"""Step 8：钉钉 @机器人 → Cursor Agent → 回群。"""

from __future__ import annotations

import logging
import sys

import dingtalk_stream
from dingtalk_stream import AckMessage

from bridge_manager import init_sdk_bridge
from conversation_store import ConversationStore
from gateway_status_notify import register_lifecycle_hooks, touch_notify_group
from inbound_dedup import InboundDedup
from inbound_message import InboundMessage, parse_inbound_message
from interrupt import is_interrupt_command
from log_redact import redact_for_log
from moa_health import probe_moa_cookie
from moa_watch import start_moa_watch
from process_guard import ensure_single_gateway_process
from agent_stream_card import is_streaming_agent_task, try_create_agent_stream_card
from progress_message import (
    build_queue_message,
    build_streaming_card_title,
    build_streaming_prompt_quote,
    build_task_ack_message,
)
from quoted_reply import quote_text_from_inbound, reply_quoted
from replay import is_replay_command
from route_patterns import should_send_text_task_ack
from task_dispatcher import TaskDispatcher
from temp_cleanup import cleanup_temp_files, start_temp_cleanup_sweeper
from log_rotate import start_log_rotate_sweeper
from cursor_runner import repo_cwd
from env_loader import load_env_local, require_env
from user_agent_pool import get_user_agent_pool

logger = logging.getLogger("dingtalk-gateway")


class GatewayBotHandler(dingtalk_stream.ChatbotHandler):
    def __init__(self, dispatcher: TaskDispatcher, store: ConversationStore) -> None:
        super().__init__()
        self._dispatcher = dispatcher
        self._store = store

    def _user_session_key(self, incoming: dingtalk_stream.ChatbotMessage) -> str:
        from user_agent_pool import UserAgentPool

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
            "sender_nick": incoming.sender_nick,
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

    def _build_task_ack(self, summary: str, *, prompt: str | None = None) -> str:
        return build_task_ack_message(summary, prompt=prompt)

    def _skip_streaming_ack(self, prompt: str | None) -> bool:
        return bool(prompt and is_streaming_agent_task(prompt))

    def _submit_task(
        self,
        incoming: dingtalk_stream.ChatbotMessage,
        inbound: InboundMessage,
        user_key: str,
        *,
        summary: str | None = None,
    ) -> None:
        """入队任务：流式任务预投放同一张卡片承载排队/待执行信息（合并原文本 ack）。

        快捷指令不发「已收到，执行中」确认语；Agent 非流式回退时仍走文本 ack。
        """
        prompt_text = inbound.prompt_text()
        summary = summary or inbound.summary_label()
        streaming = self._skip_streaming_ack(prompt_text)
        stream_card = try_create_agent_stream_card(self, incoming) if streaming else None
        if stream_card is not None:
            try:
                ahead = self._dispatcher.pending_ahead(user_key)
                if ahead > 0:
                    body = (
                        f"{build_queue_message(ahead, prompt=prompt_text)}\n"
                        "可发「中断操作」打断。"
                    )
                else:
                    body = "⏳ 已受理，准备执行…"
                stream_card.start(
                    body,
                    header="",
                    persistent_header=build_streaming_prompt_quote(prompt_text),
                    card_title=build_streaming_card_title(prompt_text),
                    start_progress=False,
                )
                self._dispatcher.enqueue(
                    incoming, inbound, user_key, stream_card=stream_card
                )
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("预投放流式卡片失败，回退文本回复: %s", exc)
                stream_card = None

        ahead = self._dispatcher.enqueue(
            incoming, inbound, user_key, stream_card=stream_card
        )

        if not should_send_text_task_ack(prompt_text):
            if ahead > 0:
                self._reply(
                    f"{build_queue_message(ahead, prompt=prompt_text)}\n"
                    "可发「中断操作」打断。",
                    incoming,
                    inbound,
                )
            return

        if ahead > 0:
            self._reply(
                f"{self._build_task_ack(summary, prompt=prompt_text)}\n"
                f"{build_queue_message(ahead, prompt=prompt_text)}\n"
                "执行中可发「中断操作」打断你的任务。",
                incoming,
                inbound,
            )
        else:
            self._reply(
                self._build_task_ack(summary, prompt=prompt_text),
                incoming,
                inbound,
            )

    async def process(self, callback: dingtalk_stream.CallbackMessage):
        incoming = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
        touch_notify_group(incoming)
        inbound = parse_inbound_message(incoming)
        user_key = self._user_session_key(incoming)
        store_kwargs = self._store_lookup_kwargs(incoming)

        if is_interrupt_command(inbound.text):
            outcome = self._dispatcher.request_cancel(user_key)
            if outcome.status is True:
                if outcome.running_streaming:
                    # 运行任务走流式卡片，卡片会显示「已被中断」，此处不重复文本；
                    # 仅当另有排队任务被取消时补一句排队取消提示。
                    if outcome.drained > 0:
                        self._reply(
                            f"✅ 已取消排队中的 {outcome.drained} 个任务。",
                            incoming,
                            inbound,
                        )
                    return AckMessage.STATUS_OK, "OK"
                if outcome.cancelled_running and outcome.drained > 0:
                    body = (
                        f"✅ 已中断你正在执行的任务，并取消了排队中的 {outcome.drained} 个任务。"
                    )
                elif outcome.cancelled_running:
                    body = "✅ 已中断你正在执行的任务。"
                else:
                    body = f"✅ 已取消排队中的 {outcome.drained} 个任务。"
                self._reply(body, incoming, inbound)
            elif outcome.status is False:
                self._reply("中断请求未能生效，请稍后重试。", incoming, inbound)
            else:
                self._reply("你当前没有正在执行的任务。", incoming, inbound)
            return AckMessage.STATUS_OK, "OK"

        if is_replay_command(inbound.text):
            last_prompt = self._store.get_last(incoming.conversation_id, **store_kwargs)
            if not last_prompt:
                self._reply("您暂无上次任务，无法重新执行。", incoming, inbound)
                return AckMessage.STATUS_OK, "OK"
            inbound = InboundMessage(text=last_prompt)
            self._submit_task(
                incoming,
                inbound,
                user_key,
                summary=f"重新执行：{last_prompt[:50]}…",
            )
            return AckMessage.STATUS_OK, "OK"

        if inbound.is_empty:
            self._reply(
                "请输入文字、图片或图文链接。常用：\n"
                "• `MOA检查` — 测试 MOA 是否可用\n"
                "• `中断操作` / `重新执行`",
                incoming,
                inbound,
            )
            return AckMessage.STATUS_OK, "OK"

        self._submit_task(incoming, inbound, user_key)
        return AckMessage.STATUS_OK, "OK"


def main() -> int:
    load_env_local()
    try:
        require_env("CURSOR_API_KEY")
        require_env("DINGTALK_CLIENT_ID")
        require_env("DINGTALK_CLIENT_SECRET")
    except RuntimeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    ensure_single_gateway_process()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_sdk_bridge(repo_cwd())

    moa_ok, moa_detail = probe_moa_cookie()
    if moa_ok:
        logger.info("启动探活 MOA: %s", moa_detail)
    else:
        logger.warning("启动探活 MOA 异常: %s", moa_detail)

    get_user_agent_pool().start_idle_sweeper()
    cleanup_temp_files()
    start_temp_cleanup_sweeper()
    start_log_rotate_sweeper()
    start_moa_watch()

    store = ConversationStore()
    dispatcher = TaskDispatcher(store)
    handler = GatewayBotHandler(dispatcher, store)
    dispatcher.bind_handler(handler)
    dispatcher.log_stale_pending_on_startup()

    credential = dingtalk_stream.Credential(
        require_env("DINGTALK_CLIENT_ID"),
        require_env("DINGTALK_CLIENT_SECRET"),
    )
    client = dingtalk_stream.DingTalkStreamClient(credential)
    client.register_callback_handler(
        dingtalk_stream.chatbot.ChatbotMessage.TOPIC,
        handler,
    )
    register_lifecycle_hooks(client)
    logger.info(
        "Yaahlan 钉钉网关已启动（fast 队列 + 按用户并行 Agent / 流式 AI 卡片 / MOA / 中断 / 持久化）"
    )
    client.start_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
