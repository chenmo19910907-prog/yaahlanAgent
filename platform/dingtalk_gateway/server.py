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
from cursor_runner import repo_cwd, run_agent_prompt
from dingtalk_media import download_message_images
from env_loader import load_env_local, require_env
from moa_health import probe_moa_cookie
from export_delivery import deliver_reply
from inbound_message import InboundMessage, parse_inbound_message
from interrupt import is_interrupt_command
from replay import is_replay_command
from reply_formatter import format_exception, format_group_reply
from task_session import TaskInterrupted, TaskSession

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

    def _conversation_id(self, incoming: dingtalk_stream.ChatbotMessage) -> str:
        return ConversationStore.conversation_key(
            incoming.conversation_id,
            incoming.sender_id,
        )

    async def process(self, callback: dingtalk_stream.CallbackMessage):
        incoming = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
        inbound = parse_inbound_message(incoming)
        conv_id = self._conversation_id(incoming)

        if is_interrupt_command(inbound.text):
            cancel_result = self._session.request_cancel(conv_id)
            if cancel_result is True:
                self.reply_text("✅ 已中断本群正在执行的操作。", incoming)
            elif cancel_result is False:
                self.reply_text(
                    "当前正在执行其它会话的任务，本群无法中断。\n"
                    f"进行中：{self._session.current_prompt()[:60]}…",
                    incoming,
                )
            else:
                self.reply_text("当前没有正在执行的任务。", incoming)
            return AckMessage.STATUS_OK, "OK"

        if is_replay_command(inbound.text):
            last_prompt = self._store.get_last(conv_id)
            if not last_prompt:
                self.reply_text("本群暂无上次任务，无法重新执行。", incoming)
                return AckMessage.STATUS_OK, "OK"
            inbound = InboundMessage(text=last_prompt)
            self.reply_text(f"已收到（重新执行：{last_prompt[:50]}…），执行中…", incoming)
            self._task_queue.put((incoming, inbound))
            return AckMessage.STATUS_OK, "OK"

        if inbound.is_empty:
            self.reply_text(
                "请输入文字、图片或图文链接。常用：\n"
                "• `帮助` — 能力说明\n"
                "• `MOA检查` — 测试 MOA 是否可用\n"
                "• `中断操作` / `重新执行`",
                incoming,
            )
            return AckMessage.STATUS_OK, "OK"

        pending = self._task_queue.qsize()
        busy = self._session.is_busy()
        if busy or pending > 0:
            ahead = pending + (1 if busy else 0)
            self.reply_text(
                f"已收到（{inbound.summary_label()}），排队中（前面约 {ahead} 个）…\n"
                "本群任务执行中可发「中断操作」打断。",
                incoming,
            )
        else:
            self.reply_text(f"已收到（{inbound.summary_label()}），执行中…", incoming)
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
                handler.reply_text(
                    "⏳ 仍在执行中… 可发「中断操作」打断本群当前任务。",
                    incoming,
                )
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
        conv_id = handler._conversation_id(incoming)
        started = time.monotonic()
        heartbeat_stop = _start_heartbeat(handler, incoming, session, conv_id)
        session.begin(prompt, conversation_id=conv_id)
        status = "error"
        try:
            logger.info(
                "开始处理 conv=%s msg=%s text=%s",
                conv_id,
                incoming.message_id,
                prompt[:120],
            )
            session.check_cancelled()

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
            else:
                raw_result = run_agent_prompt(
                    prompt,
                    image_paths=image_paths,
                    links=inbound.links,
                    session=session,
                )
                result = format_group_reply(raw_result, prompt=prompt, source="agent")
            delivery = deliver_reply(result, prompt)
            handler.reply_text(delivery.message, incoming)
            store.save(conv_id, prompt)
            status = "ok"
            if delivery.exported:
                logger.info("已导出 %s url=%s", delivery.local_path, delivery.file_url)
        except TaskInterrupted:
            status = "interrupted"
            logger.info("任务已中断 conv=%s prompt=%s", conv_id, prompt[:120])
            handler.reply_text("⚠️ 任务已被中断。", incoming)
            store.save(conv_id, prompt)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            logger.exception("任务失败 conv=%s", conv_id)
            handler.reply_text(format_exception(exc), incoming)
            store.save(conv_id, prompt)
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
    logger.info("Yaahlan 钉钉网关已启动（帮助/重试/MOA检查/本群中断/排队提示）")
    client.start_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
