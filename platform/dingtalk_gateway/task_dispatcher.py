"""任务分发：fast 队列 + 按用户 agent 队列并行。"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Any

import dingtalk_stream

from conversation_store import ConversationStore
from inbound_message import InboundMessage
from queue_persist import get_queue_persist
from route_patterns import is_likely_fast_route
from task_processor import process_inbound_task
from task_session import TaskSession

logger = logging.getLogger("dingtalk-gateway")


@dataclass(frozen=True)
class QueuedTask:
    incoming: dingtalk_stream.ChatbotMessage
    inbound: InboundMessage
    user_key: str
    lane: str


@dataclass(frozen=True)
class CancelOutcome:
    """中断请求结果：status None=空闲 False=不匹配 True=成功。"""

    status: bool | None
    drained: int = 0
    cancelled_running: bool = False


class TaskDispatcher:
    def __init__(self, store: ConversationStore) -> None:
        self._handler: Any = None
        self._store = store
        self._lock = threading.Lock()
        self._fast_queue: Queue[QueuedTask] = Queue()
        self._fast_session = TaskSession()
        self._user_queues: dict[str, Queue[QueuedTask]] = {}
        self._user_sessions: dict[str, TaskSession] = {}
        self._user_workers_started: set[str] = set()
        self._persist = get_queue_persist()
        self._fast_worker_started = False

    def bind_handler(self, handler: Any) -> None:
        self._handler = handler
        self._lock = threading.Lock()
        self._fast_queue = Queue()
        self._fast_session = TaskSession()
        self._user_queues = {}
        self._user_sessions = {}
        self._user_workers_started = set()
        self._persist = get_queue_persist()

        if not self._fast_worker_started:
            self._fast_worker_started = True
            threading.Thread(
                target=self._fast_worker_loop,
                daemon=True,
                name="gateway-fast-worker",
            ).start()

    def _user_session(self, user_key: str) -> TaskSession:
        with self._lock:
            if user_key not in self._user_sessions:
                self._user_sessions[user_key] = TaskSession()
            return self._user_sessions[user_key]

    def _drain_agent_queue(self, user_key: str) -> int:
        persist = get_queue_persist()
        drained = 0
        while True:
            with self._lock:
                queue = self._user_queues.get(user_key)
                if queue is None:
                    break
                try:
                    task = queue.get_nowait()
                except Empty:
                    break
            persist.remove(
                user_key=task.user_key,
                prompt=task.inbound.prompt_text(),
            )
            queue.task_done()
            drained += 1
        if drained:
            logger.info("已清空 agent 排队 user=%s count=%d", user_key, drained)
        return drained

    def _drain_fast_queue_for_user(self, user_key: str) -> int:
        persist = get_queue_persist()
        kept: list[QueuedTask] = []
        drained = 0
        while True:
            try:
                task = self._fast_queue.get_nowait()
            except Empty:
                break
            if task.user_key == user_key:
                persist.remove(
                    user_key=task.user_key,
                    prompt=task.inbound.prompt_text(),
                )
                self._fast_queue.task_done()
                drained += 1
            else:
                kept.append(task)
        for task in kept:
            self._fast_queue.put(task)
        if drained:
            logger.info("已清空 fast 排队 user=%s count=%d", user_key, drained)
        return drained

    def request_cancel(self, user_key: str) -> CancelOutcome:
        user_session = self._user_sessions.get(user_key)
        user_busy = user_session is not None and user_session.is_busy()
        fast_busy = (
            self._fast_session.is_busy()
            and self._fast_session.busy_conversation_id() == user_key
        )
        drained = self._drain_agent_queue(user_key) + self._drain_fast_queue_for_user(
            user_key
        )

        if not user_busy and not fast_busy:
            if drained > 0:
                return CancelOutcome(status=True, drained=drained, cancelled_running=False)
            return CancelOutcome(status=None)

        results: list[bool | None] = []
        if user_busy and user_session is not None:
            results.append(user_session.request_cancel(user_key))
        if fast_busy:
            results.append(self._fast_session.request_cancel(user_key))

        if any(result is False for result in results):
            return CancelOutcome(status=False, drained=drained, cancelled_running=False)
        if any(result is True for result in results):
            logger.info(
                "中断已分发 user=%s agent_lane=%s fast_lane=%s drained=%s",
                user_key,
                user_busy,
                fast_busy,
                drained,
            )
            return CancelOutcome(
                status=True,
                drained=drained,
                cancelled_running=True,
            )
        if drained > 0:
            return CancelOutcome(status=True, drained=drained, cancelled_running=False)
        return CancelOutcome(status=None)

    def pending_ahead(self, user_key: str) -> int:
        with self._lock:
            queue = self._user_queues.get(user_key)
            pending = queue.qsize() if queue is not None else 0
            session = self._user_sessions.get(user_key)
            busy = 1 if session is not None and session.is_busy() else 0
            fast_busy = (
                1
                if self._fast_session.is_busy()
                and self._fast_session.busy_conversation_id() == user_key
                else 0
            )
        return pending + busy + fast_busy

    def enqueue(
        self,
        incoming: dingtalk_stream.ChatbotMessage,
        inbound: InboundMessage,
        user_key: str,
    ) -> None:
        prompt = inbound.prompt_text()
        lane = "fast" if is_likely_fast_route(prompt) else "agent"
        task = QueuedTask(incoming=incoming, inbound=inbound, user_key=user_key, lane=lane)
        self._persist.add(
            user_key=user_key,
            prompt=prompt,
            lane=lane,
            conversation_id=incoming.conversation_id,
            sender_staff_id=incoming.sender_staff_id,
        )
        if lane == "fast":
            self._fast_queue.put(task)
            return
        with self._lock:
            if user_key not in self._user_queues:
                self._user_queues[user_key] = Queue()
            self._user_queues[user_key].put(task)
            if user_key not in self._user_workers_started:
                self._user_workers_started.add(user_key)
                threading.Thread(
                    target=self._agent_worker_loop,
                    args=(user_key,),
                    daemon=True,
                    name=f"gateway-agent-{user_key[:20]}",
                ).start()

    def log_stale_pending_on_startup(self) -> None:
        stale = self._persist.drain_stale_on_startup()
        if stale:
            logger.warning(
                "上次崩溃遗留 %s 条排队任务（无法自动重放钉钉消息，请用户重新 @）",
                len(stale),
            )

    def _fast_worker_loop(self) -> None:
        while True:
            task = self._fast_queue.get()
            try:
                handler = self._handler
                if handler is None:
                    logger.error("handler 未绑定，丢弃 fast 任务")
                    continue
                process_inbound_task(
                    handler,
                    task.incoming,
                    task.inbound,
                    session=self._fast_session,
                    user_key=task.user_key,
                    lane="fast",
                )
            finally:
                self._fast_queue.task_done()

    def _agent_worker_loop(self, user_key: str) -> None:
        queue = self._user_queues[user_key]
        session = self._user_session(user_key)
        while True:
            task = queue.get()
            try:
                handler = self._handler
                if handler is None:
                    logger.error("handler 未绑定，丢弃 agent 任务")
                    continue
                process_inbound_task(
                    handler,
                    task.incoming,
                    task.inbound,
                    session=session,
                    user_key=task.user_key,
                    lane="agent",
                )
            finally:
                queue.task_done()
