"""执行进度文案：排队估算、心跳已执行时长与结果耗时尾注。"""

from __future__ import annotations

from duration_history import classify_task_kind, get_duration_store
from task_session import TaskSession

# 排队时按任务数粗估等待（秒）；无历史数据时使用
QUEUE_ESTIMATE_MIN_PER_TASK = 3
DEFAULT_AGENT_ESTIMATE_S = QUEUE_ESTIMATE_MIN_PER_TASK * 60

# 自适应心跳：首次延迟与后续间隔的 clamp 范围（秒）；频率约为原配置的一半
HEARTBEAT_INITIAL_MIN_S = 80
HEARTBEAT_INITIAL_MAX_S = 180
HEARTBEAT_INTERVAL_MIN_S = 90
HEARTBEAT_INTERVAL_MAX_S = 240
HEARTBEAT_INITIAL_DEFAULT_S = 100
HEARTBEAT_INTERVAL_DEFAULT_S = 120
HEARTBEAT_MAX_COUNT = 4
HEARTBEAT_REMAINING_MIN_S = 30
# 预估剩余超过该值（秒）时，群内统一显示「3分钟以上」
ETA_DISPLAY_CAP_S = 180


def resolve_task_estimate_seconds(
    task_kind: str | None = None,
    *,
    prompt: str | None = None,
) -> float | None:
    """同类任务预计总耗时（秒）；Agent 无历史时用 DEFAULT_AGENT_ESTIMATE_S。"""
    kind = (task_kind or "").strip()
    if not kind and prompt is not None:
        kind = classify_task_kind(prompt)
    store = get_duration_store()
    estimate: float | None = None
    if kind:
        estimate = store.estimate_seconds(kind)
        if estimate is None and kind.startswith("agent:"):
            estimate = store.estimate_agent_seconds()
    if estimate is None and (not kind or kind.startswith("agent:")):
        return float(DEFAULT_AGENT_ESTIMATE_S)
    return estimate


def format_eta_total(seconds: float | None) -> str:
    """任务开始时的总耗时预估（「预计约…」）。"""
    if seconds is None or seconds <= 0:
        return ""
    if seconds > ETA_DISPLAY_CAP_S:
        return "，预计约3分钟以上"
    return f"，预计约 {format_duration(seconds)}"


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


def format_eta_remaining(seconds: float | None, *, min_show_s: float = 0) -> str:
    """格式化为「预计还需…」；超过 3 分钟显示「3分钟以上」；四舍五入为 0 秒时提示即将完成。"""
    if seconds is None:
        return ""
    if seconds <= 0 or int(round(max(0.0, seconds))) <= 0:
        return "，即将完成"
    if seconds < min_show_s:
        return ""
    if seconds > ETA_DISPLAY_CAP_S:
        return "，预计还需3分钟以上"
    return f"，预计还需约 {format_duration(seconds)}"


def build_task_ack_message(summary: str, *, prompt: str | None = None) -> str:
    """「已收到，执行中」确认语，含同类任务预估耗时。"""
    label = (summary or "").strip() or "任务"
    task_kind = classify_task_kind(prompt or "")
    estimate = resolve_task_estimate_seconds(task_kind, prompt=prompt)
    eta_part = format_eta_total(estimate)
    body = f"已收到（{label}），执行中"
    if eta_part:
        body += eta_part
    return f"{body}…"


STREAMING_HEADER_PROMPT_MAX = 120


STREAMING_CARD_LINE_BREAK = "<br>"


def build_streaming_prompt_quote(prompt: str | None) -> str:
    """用户问题原文（AI 卡片 static 区 / 兼容；单行 Markdown）。"""
    from quoted_reply import QUOTE_LABEL, _sanitize_quote_line

    text = (prompt or "").strip()
    if not text:
        return ""
    text = " ".join(text.split())
    if len(text) > STREAMING_HEADER_PROMPT_MAX:
        text = text[:STREAMING_HEADER_PROMPT_MAX].rstrip() + "…"
    return f"{QUOTE_LABEL} {_sanitize_quote_line(text)}"


def build_streaming_card_title(prompt: str | None) -> str:
    """流式卡片标题区（白线上方，纯文本）。"""
    from quoted_reply import _sanitize_quote_line

    text = (prompt or "").strip()
    if not text:
        return ""
    text = " ".join(text.split())
    if len(text) > STREAMING_HEADER_PROMPT_MAX:
        text = text[:STREAMING_HEADER_PROMPT_MAX].rstrip() + "…"
    return f"提问：{_sanitize_quote_line(text)}"


# 兼容旧名
_format_prompt_quote = build_streaming_prompt_quote


def build_streaming_ack(summary: str, *, prompt: str | None = None) -> str:
    """执行中确认语（卡片临时区，任务完成后清除）。"""
    label = (summary or "").strip() or "消息"
    task_kind = classify_task_kind(prompt or "")
    estimate = resolve_task_estimate_seconds(task_kind, prompt=prompt)
    eta_part = format_eta_total(estimate)
    body = f"已收到（{label}），执行中"
    if eta_part:
        body += eta_part
    return f"{body}… 可发「中断操作」打断。"


def build_streaming_card_header(summary: str, *, prompt: str | None = None) -> str:
    """流式卡片顶部：用户问题原文 + 确认语（合并原入队 ack 文本）。"""
    ack = build_streaming_ack(summary, prompt=prompt)
    quote = build_streaming_prompt_quote(prompt)
    if quote:
        return f"{quote}{STREAMING_CARD_LINE_BREAK}{ack}"
    return ack


def build_streaming_task_ack_message(summary: str) -> str:
    """流式卡片模式：简短确认（仅非卡片回退路径使用）。"""
    label = (summary or "").strip() or "任务"
    return (
        f"已收到（{label}），进度见下方卡片。"
        "可发「中断操作」打断。"
    )


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


def _clamp_heartbeat_seconds(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compute_heartbeat_schedule(task_kind: str | None) -> tuple[float, float]:
    """返回 (首次心跳延迟秒, 后续间隔秒)，基于同类任务历史中位数。"""
    kind = (task_kind or "").strip()
    estimate = resolve_task_estimate_seconds(kind)
    if estimate is None:
        return HEARTBEAT_INITIAL_DEFAULT_S, HEARTBEAT_INTERVAL_DEFAULT_S
    initial = _clamp_heartbeat_seconds(
        estimate * 0.8,
        HEARTBEAT_INITIAL_MIN_S,
        HEARTBEAT_INITIAL_MAX_S,
    )
    interval = _clamp_heartbeat_seconds(
        estimate * 1.0,
        HEARTBEAT_INTERVAL_MIN_S,
        HEARTBEAT_INTERVAL_MAX_S,
    )
    return initial, interval


def build_heartbeat_message(
    session: TaskSession,
    *,
    estimate_s: float | None = None,
) -> str:
    elapsed_s = session.elapsed_s()
    elapsed_str = format_duration(elapsed_s)
    parts = [f"⏳ 仍在执行中，已执行{elapsed_str}"]
    if estimate_s is not None and estimate_s > 0:
        remaining = max(0.0, estimate_s - elapsed_s)
        eta_part = format_eta_remaining(
            remaining,
            min_show_s=HEARTBEAT_REMAINING_MIN_S,
        )
        if eta_part:
            parts.append(eta_part)
    parts.append("… 可发「中断操作」打断你当前正在执行的任务。")
    return "".join(parts)
