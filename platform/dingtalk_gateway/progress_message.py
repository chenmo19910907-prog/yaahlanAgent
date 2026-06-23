"""执行进度文案：排队估算与心跳已执行时长。"""

from __future__ import annotations

from task_session import TaskSession

# 排队时按任务数粗估等待（分钟）
QUEUE_ESTIMATE_MIN_PER_TASK = 3


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


def build_queue_message(ahead: int) -> str:
    """排队提示：前面任务数 + 粗估等待。"""
    count = max(1, ahead)
    est_min = count * QUEUE_ESTIMATE_MIN_PER_TASK
    return f"排队中（前面约 {count} 个，预计等待约 {est_min} 分钟）"


def build_heartbeat_message(session: TaskSession) -> str:
    elapsed_str = format_duration(session.elapsed_s())
    return (
        f"⏳ 仍在执行中，已执行{elapsed_str}… "
        "可发「中断操作」打断本群当前任务。"
    )
