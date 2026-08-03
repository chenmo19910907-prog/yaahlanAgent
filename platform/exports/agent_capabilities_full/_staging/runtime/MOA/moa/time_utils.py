"""时间解析：支持认证过期时间自然语言输入。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_DEFAULT_TZ = ZoneInfo("Asia/Shanghai")


def resolve_expire_ms(*, expire_ms: int | None = None, expire_at: str | None = None) -> int:
    """解析过期毫秒时间戳。expire_ms 与 expire_at 二选一，expire_ms 优先。"""
    if expire_ms is not None:
        if expire_ms <= 0:
            raise ValueError("expire_ms 必须为正整数（毫秒时间戳）")
        return expire_ms
    if not expire_at or not expire_at.strip():
        raise ValueError("必须提供 --id-auth-expire-ms 或 --id-auth-expire-at")

    text = expire_at.strip().lower()
    now = datetime.now(_DEFAULT_TZ)

    if text in {"tomorrow", "明天"}:
        target = (now + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)
        return int(target.timestamp() * 1000)

    if text in {"tomorrow-start", "明天开始", "tomorrow-start-of-day"}:
        target = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return int(target.timestamp() * 1000)

    rel = re.fullmatch(r"\+(\d+)([dhm])", text)
    if rel:
        amount, unit = int(rel.group(1)), rel.group(2)
        delta = {"d": timedelta(days=amount), "h": timedelta(hours=amount), "m": timedelta(minutes=amount)}[unit]
        return int((now + delta).timestamp() * 1000)

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(expire_at.strip(), fmt)
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=23, minute=59, second=59)
            dt = dt.replace(tzinfo=_DEFAULT_TZ)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue

    raise ValueError(
        "无法解析 --id-auth-expire-at，支持：tomorrow/明天、+1d/+2h、YYYY-MM-DD HH:MM:SS"
    )


def resolve_family_fund_week_key(week: str | None = None) -> str:
    """解析家族基金周期键，格式为「周一 YYYYMMDD-week」。"""
    tz = _DEFAULT_TZ
    text = (week or "").strip()
    if not text or text.lower() in {"this", "current", "本周", "这周", "today", "今天"}:
        anchor = datetime.now(tz).date()
    else:
        if text.lower().endswith("-week"):
            text = text[:-5]
        anchor = None
        if re.fullmatch(r"\d{8}", text):
            anchor = datetime.strptime(text, "%Y%m%d").date()
        else:
            for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
                try:
                    anchor = datetime.strptime(text, fmt).date()
                    break
                except ValueError:
                    continue
        if anchor is None:
            raise ValueError(
                "无法解析 --family-fund-week，支持：YYYYMMDD、YYYY-MM-DD、this/本周，或 YYYYMMDD-week"
            )

    monday = anchor - timedelta(days=anchor.weekday())
    return f"{monday.strftime('%Y%m%d')}-week"
