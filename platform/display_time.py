"""用户可见时间：统一北京时间（Asia/Shanghai）。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

DISPLAY_TZ = ZoneInfo("Asia/Shanghai")
DISPLAY_TZ_LABEL = "北京时间"


def format_display_time(dt: datetime, *, with_label: bool = True) -> str:
    if dt.tzinfo is None:
        localized = dt.replace(tzinfo=DISPLAY_TZ)
    else:
        localized = dt.astimezone(DISPLAY_TZ)
    text = localized.strftime("%Y-%m-%d %H:%M:%S")
    return f"{text} {DISPLAY_TZ_LABEL}" if with_label else text


def now_display_time(*, with_label: bool = True) -> str:
    return format_display_time(datetime.now(DISPLAY_TZ), with_label=with_label)
