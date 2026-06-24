"""批量操作进度：Agent/脚本写入，网关轮询后推送钉钉群。"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from env_loader import GATEWAY_DIR
from batch_duration_history import get_batch_duration_store
from progress_message import format_duration, format_eta_remaining

logger = logging.getLogger("dingtalk-gateway")

PROGRESS_DIR = GATEWAY_DIR / "data" / "batch_progress"

# 群内批量进度推送最小间隔（秒）；约 30 秒～1 分钟一条
PUSH_MIN_INTERVAL_S = 30.0
# 轮询进度文件的间隔（秒）
PUSH_POLL_INTERVAL_S = 5.0
# ≥3 项才视为批量，与网关规则一致
BATCH_MIN_ITEMS = 3
# 尚无历史/进度时，按每项默认秒数粗估
DEFAULT_SEC_PER_ITEM = 1.0
# 实时进度与历史单项耗时的融合权重
LIVE_ETA_WEIGHT = 0.55
HIST_ETA_WEIGHT = 0.45


@dataclass(frozen=True)
class BatchProgressState:
    user_key: str
    total: int
    current: int
    label: str = ""
    detail: str = ""
    updated_at: float = 0.0
    started_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_key": self.user_key,
            "total": self.total,
            "current": self.current,
            "label": self.label,
            "detail": self.detail,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
        }


def _safe_filename(user_key: str) -> str:
    digest = hashlib.sha256(user_key.encode("utf-8")).hexdigest()[:24]
    return f"{digest}.json"


def _progress_path(user_key: str) -> Path:
    return PROGRESS_DIR / _safe_filename(user_key)


def report_batch_progress(
    user_key: str,
    *,
    current: int,
    total: int,
    label: str = "",
    detail: str = "",
) -> BatchProgressState:
    """写入/更新批量进度（供 CLI 与网关内脚本调用）。"""
    key = (user_key or "").strip()
    if not key:
        raise ValueError("user_key 不能为空")
    total_n = max(1, int(total))
    current_n = max(0, min(int(current), total_n))
    now = time.time()
    started_at = now
    existing = read_batch_progress(key)
    if existing is not None:
        if current_n == 0 or existing.total != total_n:
            started_at = now
        elif existing.started_at > 0:
            started_at = existing.started_at
    state = BatchProgressState(
        user_key=key,
        total=total_n,
        current=current_n,
        label=(label or "").strip(),
        detail=(detail or "").strip(),
        updated_at=now,
        started_at=started_at,
    )
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    path = _progress_path(key)
    path.write_text(
        json.dumps(state.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(
        "批量进度 user=%s %s/%s label=%s",
        key,
        current_n,
        total_n,
        state.label or "-",
    )
    if (
        current_n >= total_n
        and total_n >= BATCH_MIN_ITEMS
        and started_at > 0
        and (existing is None or existing.current < total_n or existing.total != total_n)
    ):
        duration_s = max(0.1, now - started_at)
        get_batch_duration_store().record(
            state.label,
            total=total_n,
            duration_s=duration_s,
            status="ok",
        )
    return state


def read_batch_progress(user_key: str) -> BatchProgressState | None:
    key = (user_key or "").strip()
    if not key:
        return None
    path = _progress_path(key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("读取批量进度失败 user=%s: %s", key, exc)
        return None
    if not isinstance(data, dict):
        return None
    return BatchProgressState(
        user_key=str(data.get("user_key") or key),
        total=max(1, int(data.get("total") or 1)),
        current=max(0, int(data.get("current") or 0)),
        label=str(data.get("label") or "").strip(),
        detail=str(data.get("detail") or "").strip(),
        updated_at=float(data.get("updated_at") or 0.0),
        started_at=float(data.get("started_at") or 0.0),
    )


def clear_batch_progress(user_key: str) -> None:
    key = (user_key or "").strip()
    if not key:
        return
    path = _progress_path(key)
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("清理批量进度失败 user=%s: %s", key, exc)


def _sec_per_item_estimate(state: BatchProgressState) -> float:
    """融合本次实时速度与历史单项耗时中位数。"""
    hist = get_batch_duration_store().estimate_sec_per_item(state.label)
    live: float | None = None
    if state.current > 0 and state.started_at > 0:
        elapsed = max(0.1, state.updated_at - state.started_at)
        live = elapsed / state.current
    if hist is not None and live is not None:
        return LIVE_ETA_WEIGHT * live + HIST_ETA_WEIGHT * hist
    if hist is not None:
        return hist
    if live is not None:
        return live
    return DEFAULT_SEC_PER_ITEM


def estimate_batch_remaining_s(state: BatchProgressState) -> float | None:
    """根据历史统计 + 当前进度估算剩余秒数。"""
    if state.current >= state.total:
        return None
    remaining_items = state.total - state.current
    return _sec_per_item_estimate(state) * remaining_items


def format_batch_eta_remaining(seconds: float | None) -> str:
    """格式化为群内可读的预估剩余文案；超过 3 分钟显示「3分钟以上」。"""
    return format_eta_remaining(seconds, min_show_s=0)


def is_batch_progress_active(user_key: str) -> bool:
    """批量进度进行中时，抑制「仍在执行中」心跳。"""
    state = read_batch_progress(user_key)
    if state is None or state.total < BATCH_MIN_ITEMS:
        return False
    return state.current < state.total


def build_batch_progress_message(state: BatchProgressState) -> str:
    """生成群内批量进度文案（按批量项 N/M，非项内子步骤）。"""
    label_part = f"（{state.label}）" if state.label else ""
    detail_part = f" · 当前 {state.detail}" if state.detail else ""
    if state.current >= state.total:
        return (
            f"📊 批量操作完成：共 {state.total} 项{label_part}{detail_part}"
        )
    eta_part = format_batch_eta_remaining(estimate_batch_remaining_s(state))
    return (
        f"📊 批量操作进度：已完成 {state.current}/{state.total} 项{label_part}"
        f"{detail_part}{eta_part}"
    )


def should_push_batch_progress(
    state: BatchProgressState,
    *,
    last_pushed_current: int,
    last_push_at: float,
    now: float | None = None,
) -> bool:
    """判断是否需要向群内推送本条进度（约 30 秒一条，完成时必推）。"""
    if state.current <= last_pushed_current:
        return False
    ts = now if now is not None else time.monotonic()
    if state.current >= state.total:
        return True
    if last_push_at <= 0:
        return True
    return ts - last_push_at >= PUSH_MIN_INTERVAL_S
