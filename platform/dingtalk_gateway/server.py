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
from inbound_message import InboundMessage, parse_inbound_message
from interrupt import is_interrupt_command
from log_redact import redact_for_log
from moa_health import probe_moa_cookie
from moa_watch import start_moa_watch
from process_guard import ensure_single_gateway_process
from progress_message import build_queue_message, build_task_ack_message
from quoted_reply import quote_text_from_inbound, reply_quoted
from replay import is_replay_command
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
        touch_notify_group(incoming)
        inbound = parse_inbound_message(incoming)
        user_key = self._user_session_key(incoming)
        store_kwargs = self._store_lookup_kwargs(incoming)

        if is_interrupt_command(inbound.text):
            outcome = self._dispatcher.request_cancel(user_key)
            if outcome.status is True:
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
            self._reply(
                f"{build_task_ack_message(f'重新执行：{last_prompt[:50]}…', prompt=last_prompt)}",
                incoming,
                inbound,
            )
            self._dispatcher.enqueue(incoming, inbound, user_key)
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

        ahead = self._dispatcher.pending_ahead(user_key)
        if ahead > 0:
            self._reply(
                f"{build_task_ack_message(inbound.summary_label(), prompt=inbound.prompt_text())}\n"
                f"{build_queue_message(ahead, prompt=inbound.prompt_text())}\n"
                "执行中可发「中断操作」打断你的任务。",
                incoming,
                inbound,
            )
        else:
            self._reply(
                build_task_ack_message(
                    inbound.summary_label(),
                    prompt=inbound.prompt_text(),
                ),
                incoming,
                inbound,
            )
        self._dispatcher.enqueue(incoming, inbound, user_key)
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
        "Yaahlan 钉钉网关已启动（fast 队列 + 按用户并行 Agent / 帮助 / MOA / 中断 / 持久化）"
    )
    client.start_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
