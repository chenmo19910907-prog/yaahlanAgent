"""运行中定期探活 MOA Cookie。"""

from __future__ import annotations

import logging
import threading
import time

from moa_health import probe_moa_cookie

logger = logging.getLogger("dingtalk-gateway")

DEFAULT_INTERVAL_S = 3600


def start_moa_watch(*, interval_s: float = DEFAULT_INTERVAL_S) -> None:
    def loop() -> None:
        while True:
            time.sleep(interval_s)
            try:
                ok, detail = probe_moa_cookie()
                if ok:
                    logger.info("MOA 定期探活: %s", detail)
                else:
                    logger.warning("MOA 定期探活失败: %s", detail)
            except Exception as exc:  # noqa: BLE001
                logger.warning("MOA 定期探活异常: %s", exc)

    threading.Thread(target=loop, daemon=True, name="moa-watch").start()
    logger.info("MOA 定期探活已启动（间隔 %ss）", interval_s)
