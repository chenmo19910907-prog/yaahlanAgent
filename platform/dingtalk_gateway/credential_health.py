"""Admin / Tunnel 探活（带短 TTL 缓存）。"""

from __future__ import annotations

import sys
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parent
SCRIPTS = GATEWAY_DIR.parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from credential_probe import probe_admin_token as _probe_admin_token  # noqa: E402
from credential_probe import probe_tunnel_cookie as _probe_tunnel_cookie  # noqa: E402

from credential_probe_cache import cached_probe  # noqa: E402


def probe_admin_token(*, timeout_s: float = 15.0, force: bool = False) -> tuple[bool, str]:
    return cached_probe(
        "admin_token",
        lambda: _probe_admin_token(timeout_s=timeout_s),
        force=force,
    )


def probe_tunnel_cookie(*, timeout_s: float = 15.0, force: bool = False) -> tuple[bool, str]:
    return cached_probe(
        "tunnel_cookie",
        lambda: _probe_tunnel_cookie(timeout_s=timeout_s),
        force=force,
    )


def warm_credential_probes() -> None:
    """后台预热探活缓存（不阻塞 HTTP 启动）。"""
    try:
        from moa_health import probe_moa_cookie

        probe_moa_cookie(timeout_s=20)
    except (ImportError, OSError, RuntimeError, ValueError):
        pass
    try:
        probe_admin_token(timeout_s=12.0)
    except (OSError, RuntimeError, ValueError):
        pass
    try:
        probe_tunnel_cookie(timeout_s=12.0)
    except (OSError, RuntimeError, ValueError):
        pass


__all__ = ["probe_admin_token", "probe_tunnel_cookie", "warm_credential_probes"]
