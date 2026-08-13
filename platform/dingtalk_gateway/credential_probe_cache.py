"""Admin/MOA/Tunnel 探活结果短 TTL 缓存（减少重复 HTTP/MOA 调用）。"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

_DEFAULT_TTL_S = 120.0
_lock = threading.Lock()
_cache: dict[str, tuple[float, T]] = {}


def _ttl_s() -> float:
    raw = os.environ.get("CREDENTIAL_PROBE_CACHE_TTL", "").strip()
    if not raw:
        return _DEFAULT_TTL_S
    try:
        return max(0.0, float(raw))
    except ValueError:
        return _DEFAULT_TTL_S


def get_cached(key: str) -> T | None:
    ttl = _ttl_s()
    if ttl <= 0:
        return None
    now = time.monotonic()
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        ts, value = entry
        if now - ts >= ttl:
            _cache.pop(key, None)
            return None
        return value


def set_cached(key: str, value: T) -> None:
    if _ttl_s() <= 0:
        return
    with _lock:
        _cache[key] = (time.monotonic(), value)


def invalidate_cached(key: str | None = None) -> None:
    with _lock:
        if key is None:
            _cache.clear()
        else:
            _cache.pop(key, None)


def cached_probe(
    key: str,
    probe_fn: Callable[[], T],
    *,
    force: bool = False,
) -> T:
    if not force:
        hit = get_cached(key)
        if hit is not None:
            return hit
    result = probe_fn()
    set_cached(key, result)
    return result
