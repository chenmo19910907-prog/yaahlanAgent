"""执行进度文案：心跳「仍在执行中」补充已耗时。"""

from __future__ import annotations

from task_session import TaskSession


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
    elapsed_str = format_duration(session.elapsed_s())
    return (
        f"⏳ 仍在执行中（已执行{elapsed_str}）… "
        "可发「中断操作」打断本群当前任务。"
    )
