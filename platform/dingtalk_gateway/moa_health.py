"""MOA 测试环境 Cookie 探活。"""

from __future__ import annotations

import sys
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parent
SCRIPTS = GATEWAY_DIR.parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from credential_probe import probe_moa_cookie  # noqa: F401

__all__ = ["probe_moa_cookie"]
