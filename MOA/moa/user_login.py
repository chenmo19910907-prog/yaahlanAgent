"""手机号登录态查询（queryLoginStatusV2）结果解析。"""

from __future__ import annotations

import re
from typing import Any


def resolve_phone_area_code(args: Any) -> str:
    """测试环境默认 86；线上环境（--线上环境）默认 966，见 config.online.json。"""
    explicit = getattr(args, "phone_area_code", None)
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip().lstrip("+")
    if getattr(args, "online_env", False):
        from .online_config import online_query_login_status

        return str(online_query_login_status().get("defaultAreaCode") or "966").strip()
    return "86"


def normalize_mobile_login(phone: str, area_code: str = "86") -> tuple[str, str]:
    """解析区号与手机号。支持 13311111150、+8613311111150、8613311111150。"""
    raw = str(phone or "").strip()
    if not raw:
        raise ValueError("phone 不能为空")

    area = str(area_code or "86").strip().lstrip("+")
    digits = re.sub(r"\D", "", raw.lstrip("+"))
    if not digits:
        raise ValueError(f"phone 无效: {phone}")

    if digits.startswith(area) and len(digits) > len(area):
        return area, digits[len(area) :]
    return area, digits


def _extract_user_id(data: Any) -> str | None:
    if data is None:
        return None
    if isinstance(data, str):
        text = data.strip()
        return text or None
    if isinstance(data, (int, float)):
        return str(int(data))
    if not isinstance(data, dict):
        return None

    for key in ("userId", "uid", "user_id", "momoId", "id"):
        value = data.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _is_empty_data(data: Any) -> bool:
    if data is None:
        return True
    if isinstance(data, (list, tuple, set)):
        return len(data) == 0
    if isinstance(data, dict):
        return len(data) == 0 or _extract_user_id(data) is None
    if isinstance(data, str):
        return not data.strip()
    return False


def parse_login_status_summary(
    area_code: str,
    mobile: str,
    inner_result: Any,
) -> dict[str, Any]:
    if not isinstance(inner_result, dict):
        raise RuntimeError("无法解析登录态业务返回 result（不是 object）")

    data = inner_result.get("data", inner_result)
    user_id = _extract_user_id(data)
    registered = not _is_empty_data(data) and user_id is not None

    return {
        "areaCode": str(area_code),
        "mobile": str(mobile),
        "fullNumber": f"+{area_code}{mobile}",
        "registered": registered,
        "userId": user_id,
        "data": None if _is_empty_data(data) else data,
    }
