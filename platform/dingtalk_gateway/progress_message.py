"""执行进度文案：排队估算、心跳已执行时长与结果耗时尾注。"""

from __future__ import annotations

from duration_history import classify_task_kind, get_duration_store
from task_session import TaskSession

# 排队时按任务数粗估等待（秒）；无历史数据时使用
QUEUE_ESTIMATE_MIN_PER_TASK = 3
DEFAULT_AGENT_ESTIMATE_S = QUEUE_ESTIMATE_MIN_PER_TASK * 60


def format_duration(seconds: float) -> str:
    """将秒数格式化为钉钉群可读的中文时长。"""
    total = max(0, int(round(seconds)))
    if total < 60:
        return f"{total}秒"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        if secs == 0:
            return f"{minutes}分钟"
        return f"{minutes}分{secs}秒"
    hours, minutes = divmod(minutes, 60)
    if minutes == 0:
        return f"{hours}小时"
    return f"{hours}小时{minutes}分"


def _estimate_wait_seconds(ahead: int, *, prompt: str | None = None) -> tuple[int, int]:
    """返回 (前面任务数, 预计等待秒数)。"""
    count = max(1, ahead)
    store = get_duration_store()
    task_kind = classify_task_kind(prompt or "")
    per_task = store.estimate_seconds(task_kind)
    if per_task is None and task_kind.startswith("agent:"):
        per_task = store.estimate_agent_seconds()
    if per_task is None:
        per_task = float(DEFAULT_AGENT_ESTIMATE_S)
    return count, max(30, int(round(count * per_task)))


def build_queue_message(ahead: int, *, prompt: str | None = None) -> str:
    """排队提示：前面任务数 + 预计等待（优先参考历史耗时）。"""
    count, est_s = _estimate_wait_seconds(ahead, prompt=prompt)
    est_str = format_duration(est_s)
    return f"排队中（前面约 {count} 个，预计等待约 {est_str}）"


def build_duration_footer(elapsed_s: float, *, task_kind: str | None = None) -> str:
    """最终结果尾注：本次耗时 + 同类任务历史参考。"""
    elapsed_str = format_duration(elapsed_s)
    footer = f"⏱ 本次耗时 {elapsed_str}"
    estimate = get_duration_store().estimate_seconds(task_kind)
    if estimate is not None and estimate > 0:
        footer += f"（同类任务通常约 {format_duration(estimate)}）"
    return footer


def append_duration_footer(
    message: str,
    elapsed_s: float,
    *,
    task_kind: str | None = None,
) -> str:
    """在群消息末尾追加耗时尾注。"""
    footer = build_duration_footer(elapsed_s, task_kind=task_kind)
    body = (message or "").rstrip()
    if not body:
        return footer
    return f"{body}\n\n{footer}"


def build_heartbeat_message(session: TaskSession) -> str:
    elapsed_str = format_duration(session.elapsed_s())
    return (
        f"⏳ 仍在执行中，已执行{elapsed_str}… "
        "可发「中断操作」打断你当前正在执行的任务。"
    )
