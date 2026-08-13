"""MOA 测试环境 Cookie 探活（带短 TTL 缓存）。"""

from __future__ import annotations

import sys
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parent
SCRIPTS = GATEWAY_DIR.parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from credential_probe import probe_moa_cookie as _probe_moa_cookie  # noqa: E402

from credential_probe_cache import cached_probe  # noqa: E402


def probe_moa_cookie(*, timeout_s: int = 30, force: bool = False) -> tuple[bool, str]:
    return cached_probe(
        "moa_cookie",
        lambda: _probe_moa_cookie(timeout_s=timeout_s),
        force=force,
    )


__all__ = ["probe_moa_cookie"]
