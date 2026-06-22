"""执行进度文案：心跳「仍在执行中」补充已耗时与预计剩余。"""

from __future__ import annotations

from task_session import TaskSession

DEFAULT_TASK_BUDGET_S = 600.0


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


def build_heartbeat_message(session: TaskSession) -> str:
    elapsed = session.elapsed_s()
    remaining = session.estimated_remaining_s()
    elapsed_str = format_duration(elapsed)
    if remaining is None:
        progress = f"已执行{elapsed_str}"
    elif remaining <= 0:
        progress = f"已执行{elapsed_str}，可能即将完成"
    else:
        progress = f"已执行{elapsed_str}，预计还需约{format_duration(remaining)}"
    return (
        f"⏳ 仍在执行中（{progress}）… "
        "可发「中断操作」打断本群当前任务。"
    )
