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
        self._user_outstanding: dict[str, int] = {}
        self._user_stream_submitting: set[str] = set()
        self._fast_inflight_user: str | None = None
        self._persist = get_queue_persist()
        self._submit_locks: dict[str, threading.Lock] = {}
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
        self._user_outstanding = {}
        self._user_stream_submitting = set()
        self._fast_inflight_user = None
        self._persist = get_queue_persist()
        self._submit_locks = {}

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

    @staticmethod
    def _abandon_stream_card(stream_card: Any, *, message: str = "已取消排队") -> None:
        if stream_card is None:
            return
        abandon = getattr(stream_card, "abandon_queue_waiting", None)
        if not callable(abandon):
            return
        try:
            abandon(message)
        except Exception as exc:  # noqa: BLE001
            logger.warning("排队卡 abandon 失败: %s", exc)

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
            self._abandon_stream_card(task.stream_card)
            persist.remove(
                user_key=task.user_key,
                prompt=task.inbound.prompt_text(),
            )
            self._release_outstanding(task.user_key)
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
                self._abandon_stream_card(task.stream_card)
                persist.remove(
                    user_key=task.user_key,
                    prompt=task.inbound.prompt_text(),
                )
                self._release_outstanding(task.user_key)
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

    def _finalize_cancel_state(self, user_key: str) -> None:
        self._reconcile_legacy_lane(user_key)
        with self._lock:
            self._heal_ghost_outstanding_locked(user_key)

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
            self._finalize_cancel_state(user_key)
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
            self._finalize_cancel_state(user_key)
            return CancelOutcome(
                status=True,
                drained=drained,
                cancelled_running=True,
                running_streaming=running_streaming,
            )
        self._finalize_cancel_state(user_key)
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

    def _queue_ahead_for_display_locked(self, user_key: str) -> int:
        """排队卡周期刷新：不含本卡任务自身（队尾 pending-1 + 执行中）。"""
        queue = self._user_queues.get(user_key)
        pending = queue.qsize() if queue is not None else 0
        agent_busy, agent_inflight, fast_busy, fast_inflight = (
            self._lane_active_locked(user_key)
        )
        ahead_in_queue = max(0, pending - 1)
        ahead_running = (1 if agent_busy or agent_inflight else 0) + (
            1 if fast_busy or fast_inflight else 0
        )
        return ahead_in_queue + ahead_running

    def _heal_ghost_outstanding_locked(self, user_key: str) -> None:
        """队列与 lane 均空闲时清除残留的 outstanding（中断/丢消息后易残留）。"""
        outstanding = self._user_outstanding.get(user_key, 0)
        if outstanding <= 0:
            return
        if self._pending_ahead_locked(user_key) > 0:
            return
        if user_key in self._user_stream_submitting:
            return
        logger.warning(
            "清除幽灵 outstanding user=%s was=%d",
            user_key,
            outstanding,
        )
        self._user_outstanding.pop(user_key, None)

    def _reconcile_legacy_lane(self, user_key: str) -> None:
        """单聊 canonical 化后，清掉同用户 dm: 轨道的幽灵排队/outstanding。"""
        from conversation_store import ConversationStore

        legacy = ConversationStore.legacy_dm_key(user_key)
        if not legacy:
            return
        with self._lock:
            self._heal_ghost_outstanding_locked(legacy)
        drained = self._drain_agent_queue(legacy) + self._drain_fast_queue_for_user(
            legacy
        )
        if drained:
            logger.warning(
                "已清空 legacy 轨道排队 user=%s legacy=%s count=%d",
                user_key,
                legacy,
                drained,
            )

    def _queue_ahead_before_enqueue_locked(self, user_key: str) -> int:
        self._heal_ghost_outstanding_locked(user_key)
        return max(
            self._user_outstanding.get(user_key, 0),
            self._pending_ahead_locked(user_key),
        )

    def pending_ahead(self, user_key: str) -> int:
        with self._lock:
            return self._pending_ahead_locked(user_key)

    def outstanding_count(self, user_key: str) -> int:
        with self._lock:
            return self._user_outstanding.get(user_key, 0)

    def _submit_lock(self, user_key: str) -> threading.Lock:
        with self._lock:
            lock = self._submit_locks.get(user_key)
            if lock is None:
                lock = threading.Lock()
                self._submit_locks[user_key] = lock
            return lock

    def prepare_stream_submit(self, user_key: str) -> tuple[int, bool]:
        """submit_lock 内：仅按已 commit / 执行中任务计算排队深度（不含建卡中的预占）。"""
        self._reconcile_legacy_lane(user_key)
        with self._lock:
            self._heal_ghost_outstanding_locked(user_key)
            ahead = self._pending_ahead_locked(user_key)
            show_queue = ahead > 0
            self._user_stream_submitting.add(user_key)
            return ahead, show_queue

    def rollback_stream_submit(self, user_key: str) -> None:
        with self._lock:
            self._user_stream_submitting.discard(user_key)

    def pop_last_enqueued_task(
        self, user_key: str, *, message_id: str | None
    ) -> bool:
        """流式卡片 start 失败时，撤销刚 commit 的队尾任务。"""
        persist = get_queue_persist()
        removed = False
        with self._lock:
            queue = self._user_queues.get(user_key)
            if queue is None or queue.qsize() == 0:
                return False
            items: list[QueuedTask] = []
            target: QueuedTask | None = None
            while True:
                try:
                    task = queue.get_nowait()
                except Empty:
                    break
                if (
                    not removed
                    and target is None
                    and task.incoming.message_id == message_id
                ):
                    target = task
                    removed = True
                    continue
                items.append(task)
            for task in items:
                queue.put(task)
        if target is not None:
            persist.remove(
                user_key=target.user_key,
                prompt=target.inbound.prompt_text(),
            )
            self._release_outstanding(target.user_key)
            logger.warning(
                "已撤销入队（卡片 start 失败）user=%s msg=%s",
                user_key,
                (message_id or "")[:24],
            )
        return removed

    def finish_stream_submit(self, user_key: str) -> None:
        with self._lock:
            self._user_stream_submitting.discard(user_key)

    def mark_stream_submit_started(self, user_key: str) -> None:
        with self._lock:
            self._user_stream_submitting.add(user_key)

    def mark_stream_submit_finished(self, user_key: str) -> None:
        with self._lock:
            self._user_stream_submitting.discard(user_key)

    def user_has_pending_work(self, user_key: str) -> bool:
        """该用户是否已有已 commit 未执行完的任务（含排队/执行中/流式卡片提交中）。"""
        with self._lock:
            if user_key in self._user_stream_submitting:
                return True
            if self._user_outstanding.get(user_key, 0) > 0:
                return True
            return self._pending_ahead_locked(user_key) > 0

    def resolve_stream_waiting(self, user_key: str) -> tuple[int, bool]:
        """返回 (display_ahead, should_show_queue)。False 时展示首条启动文案。"""
        self._reconcile_legacy_lane(user_key)
        with self._lock:
            self._heal_ghost_outstanding_locked(user_key)
            ahead = self._pending_ahead_locked(user_key)
        if ahead > 0:
            return ahead, True
        return 0, False

    def queue_display_ahead(self, user_key: str) -> int:
        """当前时刻该用户前面还有多少任务，供排队卡周期刷新（不含本卡任务）。"""
        self._reconcile_legacy_lane(user_key)
        with self._lock:
            self._heal_ghost_outstanding_locked(user_key)
            return self._queue_ahead_for_display_locked(user_key)

    def _enqueue_locked(self, task: QueuedTask, *, skip_outstanding_inc: bool = False) -> None:
        if task.lane == "fast":
            self._fast_queue.put(task)
            if not skip_outstanding_inc:
                self._user_outstanding[task.user_key] = (
                    self._user_outstanding.get(task.user_key, 0) + 1
                )
            return
        user_key = task.user_key
        if user_key not in self._user_queues:
            self._user_queues[user_key] = Queue()
        self._user_queues[user_key].put(task)
        if not skip_outstanding_inc:
            self._user_outstanding[user_key] = self._user_outstanding.get(user_key, 0) + 1
        if user_key not in self._user_workers_started:
            self._user_workers_started.add(user_key)
            threading.Thread(
                target=self._agent_worker_loop,
                args=(user_key,),
                daemon=True,
                name=f"gateway-agent-{user_key[:20]}",
            ).start()

    def _release_outstanding(self, user_key: str) -> None:
        with self._lock:
            count = self._user_outstanding.get(user_key, 0)
            if count <= 1:
                self._user_outstanding.pop(user_key, None)
            else:
                self._user_outstanding[user_key] = count - 1

    @staticmethod
    def _mark_stream_card_picked_up(stream_card: Any) -> None:
        if stream_card is None:
            return
        mark = getattr(stream_card, "mark_worker_picked_up", None)
        if not callable(mark):
            return
        try:
            mark()
        except Exception as exc:  # noqa: BLE001
            logger.warning("mark_worker_picked_up 失败: %s", exc)

    def commit_enqueued_task(
        self,
        incoming: dingtalk_stream.ChatbotMessage,
        inbound: InboundMessage,
        user_key: str,
        *,
        stream_card: Any = None,
        outstanding_pre_reserved: bool = False,
    ) -> None:
        """流式卡片 start 完成后入队（调用方须已持有该 user 的 submit_lock）。"""
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
            self._enqueue_locked(
                task,
                skip_outstanding_inc=outstanding_pre_reserved,
            )

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
            self._enqueue_locked(task)
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
                self._mark_stream_card_picked_up(task.stream_card)
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
                self._release_outstanding(task.user_key)
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
                self._mark_stream_card_picked_up(task.stream_card)
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
                self._release_outstanding(user_key)
                queue.task_done()
