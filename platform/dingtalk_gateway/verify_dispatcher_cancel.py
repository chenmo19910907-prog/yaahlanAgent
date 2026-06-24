#!/usr/bin/env python3
"""离线验证：fast / agent 双通道中断分发与排队清空。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from queue import Queue
from unittest.mock import MagicMock

from conversation_store import ConversationStore
from inbound_message import InboundMessage
from task_dispatcher import CancelOutcome, QueuedTask, TaskDispatcher


def _fake_task(user_key: str, prompt: str) -> QueuedTask:
    incoming = MagicMock()
    incoming.conversation_id = user_key.split(":")[0]
    incoming.sender_staff_id = "WB001"
    inbound = InboundMessage(text=prompt)
    return QueuedTask(incoming=incoming, inbound=inbound, user_key=user_key, lane="agent")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        store = ConversationStore(index_path=Path(tmp) / "conversations.json")
        dispatcher = TaskDispatcher(store)
        user_a = "cidgroup:user:WB001"
        user_b = "cidgroup:user:WB002"

        # 空闲时中断
        if dispatcher.request_cancel(user_a) != CancelOutcome(status=None):
            print("[FAIL] idle cancel should be CancelOutcome(None)", file=sys.stderr)
            return 1
        print("[OK] idle => None")

        # fast 通道：仅 _fast_session 忙
        dispatcher._fast_session.begin("MOA检查", conversation_id=user_a)
        got = dispatcher.request_cancel(user_a)
        if got != CancelOutcome(status=True, cancelled_running=True):
            print(f"[FAIL] fast busy cancel => {got!r}", file=sys.stderr)
            return 1
        if not dispatcher._fast_session.cancel_requested():
            print("[FAIL] fast session cancel flag not set", file=sys.stderr)
            return 1
        dispatcher._fast_session.end()
        print("[OK] fast lane cancel")

        # 其他用户 fast 忙时不应误中断
        dispatcher._fast_session.begin("环境检查", conversation_id=user_a)
        if dispatcher.request_cancel(user_b) != CancelOutcome(status=None):
            print("[FAIL] other user should not cancel fast task", file=sys.stderr)
            return 1
        dispatcher._fast_session.end()
        print("[OK] fast lane isolated by user_key")

        # agent 通道
        agent_session = dispatcher._user_session(user_a)
        agent_session.begin("查用户详情", conversation_id=user_a)
        if dispatcher.request_cancel(user_a) != CancelOutcome(status=True, cancelled_running=True):
            print("[FAIL] agent lane cancel failed", file=sys.stderr)
            return 1
        agent_session.end()
        print("[OK] agent lane cancel")

        # pending_ahead 计入 fast 忙
        dispatcher._fast_session.begin("2.4.5版本生成测试报告", conversation_id=user_a)
        ahead = dispatcher.pending_ahead(user_a)
        dispatcher._fast_session.end()
        if ahead < 1:
            print(f"[FAIL] pending_ahead with fast busy => {ahead}", file=sys.stderr)
            return 1
        print(f"[OK] pending_ahead includes fast busy ({ahead})")

        # pending_ahead / 中断 计入 agent inflight（已出队未 begin）
        with dispatcher._lock:
            dispatcher._user_inflight.add(user_a)
        ahead = dispatcher.pending_ahead(user_a)
        got = dispatcher.request_cancel(user_a)
        with dispatcher._lock:
            dispatcher._user_inflight.discard(user_a)
        if ahead < 1:
            print(f"[FAIL] pending_ahead with agent inflight => {ahead}", file=sys.stderr)
            return 1
        if got != CancelOutcome(status=True, cancelled_running=True):
            print(f"[FAIL] inflight-only cancel => {got!r}", file=sys.stderr)
            return 1
        print("[OK] agent inflight pending + cancel")

        # busy + 队列各 1 条 => pending_ahead 为 2
        agent_session.begin("占用中", conversation_id=user_a)
        dispatcher._user_queues[user_a] = Queue()
        dispatcher._user_queues[user_a].put(_fake_task(user_a, "排队任务A"))
        ahead = dispatcher.pending_ahead(user_a)
        agent_session.end()
        if ahead != 2:
            print(f"[FAIL] pending_ahead busy+queued => {ahead}", file=sys.stderr)
            return 1
        print("[OK] pending_ahead busy + queued")

        # 仅 agent 排队、未执行时也可取消
        dispatcher._user_queues[user_a] = Queue()
        dispatcher._user_queues[user_a].put(_fake_task(user_a, "排队任务1"))
        got = dispatcher.request_cancel(user_a)
        if got != CancelOutcome(status=True, drained=1, cancelled_running=False):
            print(f"[FAIL] agent queued-only cancel => {got!r}", file=sys.stderr)
            return 1
        if dispatcher._user_queues[user_a].qsize() != 0:
            print("[FAIL] agent queue not drained", file=sys.stderr)
            return 1
        print("[OK] agent queued tasks cancelled")

        # fast 排队清空（仅放本用户任务，避免 worker 竞态消费他人任务）
        dispatcher._fast_queue.put(_fake_task(user_a, "fast排队"))
        drained = dispatcher._drain_fast_queue_for_user(user_a)
        if drained != 1:
            print(f"[FAIL] fast drain => drained={drained}", file=sys.stderr)
            return 1
        print("[OK] fast queued tasks cancelled for user")

    print("[PASS] dispatcher cancel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
