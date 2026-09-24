# -*- coding: utf-8 -*-
"""后台 melon-gateway 调用封装（确认应得薪资等）。

算薪 pytest 的 MOA1/MOA2 仍走 utils/moa_utils.py。
确认应得薪资必须走本模块（sso-token + yaahlan-jwt），不要打 Redis MOA。
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REPO_ROOT = os.path.normpath(os.path.join(PROJECT_ROOT, ".."))
_GATEWAY_SCRIPTS = os.path.join(REPO_ROOT, ".cursor/skills/moa-call/scripts")
if not os.path.isdir(_GATEWAY_SCRIPTS):
    _GATEWAY_SCRIPTS = os.path.join(PROJECT_ROOT, ".cursor/skills/moa-call/scripts")
if _GATEWAY_SCRIPTS not in sys.path:
    sys.path.insert(0, _GATEWAY_SCRIPTS)

from gateway_call import (  # noqa: E402
    GatewayAuthError,
    GatewayConfigError,
    _load_dotenv,
    call_named_endpoint,
    resolve_credentials,
)

CONFIRM_ENDPOINT = "confirm_salary_by_area"
ENV_RUN_CONFIRM = "RUN_CONFIRM_BY_AREA"


def confirm_by_area_enabled() -> bool:
    return os.environ.get(ENV_RUN_CONFIRM, "").strip().lower() in ("1", "true", "yes")


def credentials_available() -> tuple[bool, str]:
    _load_dotenv()
    try:
        resolve_credentials(None, None)
        return True, ""
    except SystemExit as exc:
        return False, str(exc)
    except GatewayAuthError as exc:
        return False, str(exc)


def confirm_salary_by_area(start_date: str, area: str, *, timeout: int = 120) -> dict:
    """按大区确认指定结算周期。写操作，调用前须已通过 RUN_CONFIRM_BY_AREA 闸门。"""
    return call_named_endpoint(
        CONFIRM_ENDPOINT,
        {"startDate": str(start_date), "area": str(area)},
        confirm=True,
        timeout=timeout,
    )


__all__ = [
    "CONFIRM_ENDPOINT",
    "ENV_RUN_CONFIRM",
    "GatewayAuthError",
    "GatewayConfigError",
    "confirm_by_area_enabled",
    "confirm_salary_by_area",
    "credentials_available",
]
