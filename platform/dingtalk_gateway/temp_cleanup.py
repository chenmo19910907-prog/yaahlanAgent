"""清理网关临时目录中的过期文件。"""

from __future__ import annotations

import logging
import shutil
import threading
import time
from pathlib import Path

from dingtalk_media import ATTACHMENTS_DIR
from env_loader import GATEWAY_DIR

logger = logging.getLogger("dingtalk-gateway")

EXPORTS_DIR = GATEWAY_DIR / "exports"
DEFAULT_MAX_AGE_S = 7 * 24 * 3600
SWEEPER_INTERVAL_S = 24 * 3600

_CLEANUP_DIRS = (
    ATTACHMENTS_DIR,
    EXPORTS_DIR,
    EXPORTS_DIR / "catalog",
    EXPORTS_DIR / "reports",
)


def _dir_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def cleanup_temp_files(*, max_age_s: float = DEFAULT_MAX_AGE_S) -> dict[str, int]:
    """删除超过 max_age_s 的临时文件/目录，返回各目录删除计数。"""
    cutoff = time.time() - max_age_s
    stats: dict[str, int] = {}

    for root in _CLEANUP_DIRS:
        if not root.is_dir():
            stats[str(root)] = 0
            continue
        removed = 0
        for entry in root.iterdir():
            try:
                mtime = _dir_mtime(entry)
                if mtime >= cutoff:
                    continue
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
                removed += 1
            except OSError as exc:
                logger.warning("清理临时文件失败 path=%s: %s", entry, exc)
        stats[str(root.name)] = removed

    total = sum(stats.values())
    if total:
        logger.info("临时文件清理完成，共删除 %s 项: %s", total, stats)
    return stats


def start_temp_cleanup_sweeper(
    *,
    interval_s: float = SWEEPER_INTERVAL_S,
    max_age_s: float = DEFAULT_MAX_AGE_S,
) -> None:
    def loop() -> None:
        while True:
            time.sleep(interval_s)
            try:
                cleanup_temp_files(max_age_s=max_age_s)
            except Exception as exc:  # noqa: BLE001
                logger.warning("临时文件 sweep 失败: %s", exc)

    threading.Thread(target=loop, daemon=True, name="temp-cleanup-sweeper").start()
    logger.info("临时文件 sweep 已启动（TTL=%ss，间隔=%ss）", max_age_s, interval_s)
