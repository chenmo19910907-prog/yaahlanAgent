"""网关日志按大小轮转。"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from env_loader import GATEWAY_DIR

logger = logging.getLogger("dingtalk-gateway")

LOG_DIR = GATEWAY_DIR / "logs"
MAX_BYTES = 5 * 1024 * 1024
SWEEP_INTERVAL_S = 24 * 3600


def rotate_file(path: Path, *, max_bytes: int = MAX_BYTES) -> bool:
    if not path.is_file():
        return False
    try:
        if path.stat().st_size < max_bytes:
            return False
    except OSError:
        return False
    backup = path.with_name(path.name + ".1")
    try:
        if backup.is_file():
            backup.unlink()
        path.rename(backup)
        path.touch()
        logger.info("日志已轮转 %s → %s", path.name, backup.name)
        return True
    except OSError as exc:
        logger.warning("日志轮转失败 %s: %s", path, exc)
        return False


def rotate_gateway_logs() -> int:
    count = 0
    for name in ("gateway.log", "gateway.err.log"):
        if rotate_file(LOG_DIR / name):
            count += 1
    return count


def start_log_rotate_sweeper(*, interval_s: float = SWEEP_INTERVAL_S) -> None:
    def loop() -> None:
        while True:
            time.sleep(interval_s)
            try:
                rotate_gateway_logs()
            except Exception as exc:  # noqa: BLE001
                logger.warning("日志轮转 sweep 失败: %s", exc)

    threading.Thread(target=loop, daemon=True, name="log-rotate-sweeper").start()
    rotate_gateway_logs()
    logger.info("日志轮转 sweep 已启动（上限 %sMB）", MAX_BYTES // (1024 * 1024))
