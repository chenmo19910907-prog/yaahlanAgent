"""MDP Nova 用户注销（userAdmin/cancelUser）校验与响应解析。"""

from __future__ import annotations

import re
from typing import Any

from .gift import mdp_gift_success as mdp_user_admin_success

DEFAULT_PROTECTED_PHONE_MIN = 13311111111
DEFAULT_PROTECTED_PHONE_MAX = 13311111130


def normalize_phone_digits(phone: Any) -> int | None:
    if phone is None:
        return None
    digits = re.sub(r"\D", "", str(phone).strip())
    if not digits:
        return None
    # +8613311111111 → 13311111111
    if digits.startswith("86") and len(digits) > 11:
        digits = digits[2:]
    try:
        return int(digits)
    except ValueError:
        return None


def is_protected_test_phone(
    phone: Any,
    *,
    min_phone: int = DEFAULT_PROTECTED_PHONE_MIN,
    max_phone: int = DEFAULT_PROTECTED_PHONE_MAX,
) -> bool:
    digits = normalize_phone_digits(phone)
    if digits is None:
        return False
    return min_phone <= digits <= max_phone


def protected_phone_range_label(
    *,
    min_phone: int = DEFAULT_PROTECTED_PHONE_MIN,
    max_phone: int = DEFAULT_PROTECTED_PHONE_MAX,
) -> str:
    return f"{min_phone}~{max_phone}"


def assert_cancel_user_allowed(
    *,
    user_id: str,
    phone: Any,
    min_phone: int = DEFAULT_PROTECTED_PHONE_MIN,
    max_phone: int = DEFAULT_PROTECTED_PHONE_MAX,
) -> None:
    if is_protected_test_phone(phone, min_phone=min_phone, max_phone=max_phone):
        digits = normalize_phone_digits(phone)
        raise ValueError(
            f"禁止注销：手机号 {digits} 属于受保护测试号段 "
            f"{protected_phone_range_label(min_phone=min_phone, max_phone=max_phone)}"
        )
    if not str(user_id or "").strip():
        raise ValueError("cancel-user-id 不能为空")


def parse_cancel_user_summary(resp: dict[str, Any], *, user_id: str) -> dict[str, Any]:
    ok = mdp_user_admin_success(resp.get("ec"))
    return {
        "userId": str(user_id).strip(),
        "success": ok,
        "ec": resp.get("ec"),
        "em": resp.get("em"),
        "data": resp.get("data"),
    }
