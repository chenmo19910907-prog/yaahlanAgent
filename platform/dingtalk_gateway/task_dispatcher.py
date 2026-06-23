"""任务分发：fast 队列 + 按用户 agent 队列并行。"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from queue import Queue
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

        threading.Thread(
            target=self._fast_worker_loop,
            daemon=True,
            name="gateway-fast-worker",
        ).start()

    def bind_handler(self, handler: Any) -> None:
        self._handler = handler
        self._lock = threading.Lock()
        self._fast_queue: Queue[QueuedTask] = Queue()
        self._fast_session = TaskSession()
        self._user_queues: dict[str, Queue[QueuedTask]] = {}
        self._user_sessions: dict[str, TaskSession] = {}
        self._user_workers_started: set[str] = set()
        self._persist = get_queue_persist()

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

    def request_cancel(self, user_key: str) -> bool | None:
        session = self._user_sessions.get(user_key)
        if session is None or not session.is_busy():
            return None
        return session.request_cancel(user_key)

    def pending_ahead(self, user_key: str) -> int:
        with self._lock:
            queue = self._user_queues.get(user_key)
            pending = queue.qsize() if queue is not None else 0
            session = self._user_sessions.get(user_key)
            busy = 1 if session is not None and session.is_busy() else 0
        return pending + busy

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
                )
            finally:
                queue.task_done()
