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

        # 连发两问：第一条已 commit 在队时，第二条应显示排队且 ahead=1
        dispatcher._user_queues[user_a] = Queue()
        dispatcher._user_queues[user_a].put(_fake_task(user_a, "第一个问题"))
        dispatcher._user_outstanding[user_a] = 1
        display2, show2 = dispatcher.prepare_stream_submit(user_a)
        if not show2 or display2 != 1:
            print(
                f"[FAIL] prepare before second commit => show={show2} display={display2}",
                file=sys.stderr,
            )
            return 1
        dispatcher.finish_stream_submit(user_a)
        ahead2 = dispatcher.enqueue(
            _fake_task(user_a, "第二个问题").incoming,
            InboundMessage(text="第二个问题"),
            user_a,
        )
        if ahead2 != 1:
            print(f"[FAIL] second enqueue ahead => {ahead2}", file=sys.stderr)
            return 1
        print("[OK] sequential double submit ahead counts")

        # 空闲连发：第一条仅 prepare 尚未 commit 时，第二条不应误判排队
        dispatcher5 = TaskDispatcher(ConversationStore(index_path=Path(tmp) / "c5.json"))
        user_e = "cidgroup:user:WB006"
        d1, s1 = dispatcher5.prepare_stream_submit(user_e)
        d2, s2 = dispatcher5.prepare_stream_submit(user_e)
        dispatcher5.finish_stream_submit(user_e)
        if s1 or s2 or d1 != 0 or d2 != 0:
            print(
                f"[FAIL] idle double prepare should not queue => "
                f"s1={s1} s2={s2} d1={d1} d2={d2}",
                file=sys.stderr,
            )
            return 1
        print("[OK] idle double prepare not queued")

        # 首条消息：resolve 在 mark_stream_submit_started 之前，不应误判排队
        dispatcher3 = TaskDispatcher(ConversationStore(index_path=Path(tmp) / "c3.json"))
        user_c = "cidgroup:user:WB003"
        display0, show0 = dispatcher3.resolve_stream_waiting(user_c)
        if show0 or display0 != 0:
            print(
                f"[FAIL] first message should not queue => show={show0} display={display0}",
                file=sys.stderr,
            )
            return 1
        dispatcher3.mark_stream_submit_started(user_c)
        display_bad, show_bad = dispatcher3.resolve_stream_waiting(user_c)
        dispatcher3.mark_stream_submit_finished(user_c)
        if show_bad or display_bad != 0:
            print(
                "[FAIL] resolve after mark_stream_submit_started must not use submitting flag",
                file=sys.stderr,
            )
            return 1
        print("[OK] first message not queued")

        # worker 已 dequeue 但 ahead 短暂为 0：lane 仍 busy 时应展示排队
        dispatcher2 = TaskDispatcher(ConversationStore(index_path=Path(tmp) / "conversations2.json"))
        user_b = "cidgroup:user:WB002"
        with dispatcher2._lock:
            dispatcher2._user_inflight.add(user_b)
        display, show = dispatcher2.resolve_stream_waiting(user_b)
        if not show or display != 1:
            print(
                f"[FAIL] race with inflight only => show={show} display={display}",
                file=sys.stderr,
            )
            return 1
        dispatcher2._user_queues[user_b] = Queue()
        dispatcher2._user_queues[user_b].put(_fake_task(user_b, "第二个"))
        dispatcher2._user_outstanding[user_b] = 1
        display2, show2 = dispatcher2.resolve_stream_waiting(user_b)
        if not show2 or display2 != 1:
            print(
                f"[FAIL] race with inflight+outstanding => show={show2} display={display2}",
                file=sys.stderr,
            )
            return 1
        print("[OK] resolve_stream_waiting outstanding race")

        # 幽灵 outstanding 不影响 resolve（只看 pending）
        dispatcher4 = TaskDispatcher(ConversationStore(index_path=Path(tmp) / "c4.json"))
        user_d = "cidgroup:user:WB004"
        with dispatcher4._lock:
            dispatcher4._user_outstanding[user_d] = 2
        display_g, show_g = dispatcher4.resolve_stream_waiting(user_d)
        if show_g or display_g != 0:
            print(
                f"[FAIL] ghost outstanding should not queue => show={show_g} display={display_g}",
                file=sys.stderr,
            )
            return 1
        print("[OK] ghost outstanding ignored for queue depth")

        # legacy dm: 轨道残留 outstanding，canonical 入队前应清掉
        user_canon = "cidbot:user:WB005"
        user_legacy = "dm:WB005"
        with dispatcher4._lock:
            dispatcher4._user_outstanding[user_legacy] = 1
        display_l, show_l = dispatcher4.resolve_stream_waiting(user_canon)
        if show_l or display_l != 0:
            print(
                f"[FAIL] legacy ghost should not block canonical => show={show_l}",
                file=sys.stderr,
            )
            return 1
        print("[OK] legacy dm lane reconciled")

        # queue_display_ahead 不含本卡任务（首条 commit 后队列为 1 时不应显示排队）
        dispatcher6 = TaskDispatcher(ConversationStore(index_path=Path(tmp) / "c6.json"))
        user_f = "cidgroup:user:WB007"
        with dispatcher6._lock:
            dispatcher6._user_queues[user_f] = Queue()
            dispatcher6._user_queues[user_f].put(_fake_task(user_f, "首条"))
            dispatcher6._user_outstanding[user_f] = 1
        if dispatcher6.queue_display_ahead(user_f) != 0:
            print(
                f"[FAIL] display ahead should exclude self => "
                f"{dispatcher6.queue_display_ahead(user_f)}",
                file=sys.stderr,
            )
            return 1
        agent_session_f = dispatcher6._user_session(user_f)
        agent_session_f.begin("占用", conversation_id=user_f)
        if dispatcher6.queue_display_ahead(user_f) != 1:
            print(
                f"[FAIL] display ahead with busy should be 1 => "
                f"{dispatcher6.queue_display_ahead(user_f)}",
                file=sys.stderr,
            )
            return 1
        agent_session_f.end()
        dispatcher6._user_queues[user_f].put(_fake_task(user_f, "第二条"))
        if dispatcher6.queue_display_ahead(user_f) != 1:
            print(
                f"[FAIL] second task waiting => {dispatcher6.queue_display_ahead(user_f)}",
                file=sys.stderr,
            )
            return 1
        print("[OK] queue_display_ahead excludes self")

    print("[PASS] dispatcher cancel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
