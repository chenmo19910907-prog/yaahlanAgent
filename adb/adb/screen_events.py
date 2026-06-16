"""屏幕监视：跨进程触控事件记录（供 watch 页面叠加反馈）。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_MODULE_ROOT = Path(__file__).resolve().parent.parent
WATCH_DIR = _MODULE_ROOT / ".watch"
EVENTS_FILE = WATCH_DIR / "events.jsonl"
MAX_EVENTS = 300


def _ensure_dir() -> None:
    WATCH_DIR.mkdir(parents=True, exist_ok=True)


def emit_event(
    kind: str,
    *,
    serial: str | None = None,
    **fields: Any,
) -> None:
    """记录 tap / swipe / key 等操作，供 watch 前端绘制反馈。"""
    _ensure_dir()
    payload: dict[str, Any] = {
        "t": time.time(),
        "kind": kind,
        "serial": serial,
        **fields,
    }
    with EVENTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    _prune_events()


def _prune_events() -> None:
    if not EVENTS_FILE.is_file():
        return
    lines = EVENTS_FILE.read_text(encoding="utf-8").splitlines()
    if len(lines) <= MAX_EVENTS:
        return
    tail = lines[-MAX_EVENTS:]
    EVENTS_FILE.write_text("\n".join(tail) + "\n", encoding="utf-8")


def read_events(*, since: float | None = None, limit: int = 80) -> list[dict[str, Any]]:
    if not EVENTS_FILE.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in EVENTS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since is not None and float(item.get("t", 0)) < since:
            continue
        out.append(item)
    return out[-limit:]


def clear_events() -> None:
    _ensure_dir()
    EVENTS_FILE.write_text("", encoding="utf-8")
