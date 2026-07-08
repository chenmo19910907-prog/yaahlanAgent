"""任务分发：fast 队列 + 按用户 agent 队列并行。"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Any

import dingtalk_stream

from agent_stream_card import is_agent_streaming_enabled
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
    # 入队时预投放的流式卡片（承载排队信息，执行时复用），可为 None
    stream_card: Any = None


@dataclass(frozen=True)
class CancelOutcome:
    """中断请求结果：status None=空闲 False=不匹配 True=成功。"""

    status: bool | None
    drained: int = 0
    cancelled_running: bool = False
    # 被中断的运行任务是否走流式卡片（卡片会自行显示中断状态，无需重复文本回复）
    running_streaming: bool = False


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
        self._user_inflight: set[str] = set()
        self._fast_inflight_user: str | None = None
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
        self._user_inflight = set()
        self._fast_inflight_user = None
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

    def _lane_active_locked(self, user_key: str) -> tuple[bool, bool, bool, bool]:
        """返回 (agent_busy, agent_inflight, fast_busy, fast_inflight)。"""
        session = self._user_sessions.get(user_key)
        agent_busy = session is not None and session.is_busy()
        agent_inflight = user_key in self._user_inflight
        fast_busy = (
            self._fast_session.is_busy()
            and self._fast_session.busy_conversation_id() == user_key
        )
        fast_inflight = self._fast_inflight_user == user_key
        return agent_busy, agent_inflight, fast_busy, fast_inflight

    def request_cancel(self, user_key: str) -> CancelOutcome:
        with self._lock:
            user_session = self._user_sessions.get(user_key)
            agent_busy, agent_inflight, fast_busy, fast_inflight = (
                self._lane_active_locked(user_key)
            )
        drained = self._drain_agent_queue(user_key) + self._drain_fast_queue_for_user(
            user_key
        )

        agent_active = agent_busy or agent_inflight
        fast_active = fast_busy or fast_inflight
        if not agent_active and not fast_active:
            if drained > 0:
                return CancelOutcome(status=True, drained=drained, cancelled_running=False)
            return CancelOutcome(status=None)

        results: list[bool | None] = []
        agent_running_cancelled = False
        if agent_active:
            session = user_session or self._user_session(user_key)
            if agent_inflight and not agent_busy:
                session.arm_cancel()
                results.append(True)
            elif agent_busy:
                cancel_result = session.request_cancel(user_key)
                results.append(cancel_result)
                if cancel_result is True:
                    agent_running_cancelled = True
        if fast_active:
            if fast_inflight and not fast_busy:
                self._fast_session.arm_cancel()
                results.append(True)
            elif fast_busy:
                results.append(self._fast_session.request_cancel(user_key))

        if any(result is False for result in results):
            return CancelOutcome(status=False, drained=drained, cancelled_running=False)
        if any(result is True for result in results):
            logger.info(
                "中断已分发 user=%s agent_active=%s fast_active=%s drained=%s",
                user_key,
                agent_active,
                fast_active,
                drained,
            )
            running_streaming = (
                agent_running_cancelled and is_agent_streaming_enabled()
            )
            return CancelOutcome(
                status=True,
                drained=drained,
                cancelled_running=True,
                running_streaming=running_streaming,
            )
        if drained > 0:
            return CancelOutcome(status=True, drained=drained, cancelled_running=False)
        return CancelOutcome(status=None)

    def _pending_ahead_locked(self, user_key: str) -> int:
        queue = self._user_queues.get(user_key)
        pending = queue.qsize() if queue is not None else 0
        agent_busy, agent_inflight, fast_busy, fast_inflight = (
            self._lane_active_locked(user_key)
        )
        agent_active = 1 if agent_busy or agent_inflight else 0
        fast_active = 1 if fast_busy or fast_inflight else 0
        return pending + agent_active + fast_active

    def pending_ahead(self, user_key: str) -> int:
        with self._lock:
            return self._pending_ahead_locked(user_key)

    def enqueue(
        self,
        incoming: dingtalk_stream.ChatbotMessage,
        inbound: InboundMessage,
        user_key: str,
        *,
        stream_card: Any = None,
    ) -> int:
        """入队并返回本任务前面的任务数（含执行中 / 已出队未 begin）。"""
        prompt = inbound.prompt_text()
        lane = "fast" if is_likely_fast_route(prompt) else "agent"
        task = QueuedTask(
            incoming=incoming,
            inbound=inbound,
            user_key=user_key,
            lane=lane,
            stream_card=stream_card,
        )
        self._persist.add(
            user_key=user_key,
            prompt=prompt,
            lane=lane,
            conversation_id=incoming.conversation_id,
            sender_staff_id=incoming.sender_staff_id,
        )
        with self._lock:
            ahead = self._pending_ahead_locked(user_key)
            if lane == "fast":
                self._fast_queue.put(task)
            else:
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
            return ahead

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
            with self._lock:
                self._fast_inflight_user = task.user_key
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
                    preassigned_card=task.stream_card,
                )
            finally:
                with self._lock:
                    if self._fast_inflight_user == task.user_key:
                        self._fast_inflight_user = None
                self._fast_queue.task_done()

    def _agent_worker_loop(self, user_key: str) -> None:
        queue = self._user_queues[user_key]
        session = self._user_session(user_key)
        while True:
            task = queue.get()
            with self._lock:
                self._user_inflight.add(user_key)
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
                    preassigned_card=task.stream_card,
                )
            finally:
                with self._lock:
                    self._user_inflight.discard(user_key)
                queue.task_done()
