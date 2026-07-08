"""入站消息去重：防止钉钉 webhook 重试或连点导致重复入队。"""

from __future__ import annotations

import threading
import time

MESSAGE_ID_TTL_S = 600.0
# 同用户同文案极短时间内的重复提交（连点发送）
PROMPT_BURST_WINDOW_S = 3.0


class InboundDedup:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._message_ids: dict[str, float] = {}
        self._recent_prompts: dict[tuple[str, str], float] = {}

    def _purge_expired(self, now: float) -> None:
        for store, ttl in (
            (self._message_ids, MESSAGE_ID_TTL_S),
            (self._recent_prompts, PROMPT_BURST_WINDOW_S),
        ):
            stale = [key for key, ts in store.items() if now - ts > ttl]
            for key in stale:
                del store[key]

    def should_skip(
        self,
        *,
        message_id: str,
        user_key: str,
        prompt: str,
    ) -> str | None:
        """返回跳过原因；None 表示可处理。"""
        now = time.monotonic()
        with self._lock:
            self._purge_expired(now)
            mid = (message_id or "").strip()
            if mid:
                if mid in self._message_ids:
                    return f"duplicate message_id={mid}"
                self._message_ids[mid] = now
            text = (prompt or "").strip()
            if text:
                burst_key = (user_key, text)
                last = self._recent_prompts.get(burst_key)
                if last is not None and now - last < PROMPT_BURST_WINDOW_S:
                    return "duplicate prompt burst"
                self._recent_prompts[burst_key] = now
        return None
