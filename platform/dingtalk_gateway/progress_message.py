"""执行进度文案：排队估算、心跳阶段与剩余时间。"""

from __future__ import annotations

from task_session import TaskSession

PHASE_LABELS: dict[str, str] = {
    "prepare": "准备中",
    "route": "快捷指令",
    "agent": "Agent 执行中",
    "export": "导出处理中",
    "reply": "整理回复中",
}

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
    phase_label = PHASE_LABELS.get(session.phase(), "")
    parts: list[str] = ["⏳ 仍在执行中"]
    if phase_label:
        parts.append(f"（{phase_label}）")
    parts.append(f"已执行{elapsed_str}")

    remaining = session.estimated_remaining_s()
    if remaining is not None and remaining > 30:
        parts.append(f"预计还需{format_duration(remaining)}")
    elif remaining is not None and remaining <= 30:
        parts.append("已接近时限，可能即将完成")

    body = "，".join(parts)
    return f"{body}… 可发「中断操作」打断本群当前任务。"
