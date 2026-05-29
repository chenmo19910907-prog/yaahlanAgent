"""VIP 信息查询结果解析。"""

from __future__ import annotations

from typing import Any

from .config import level_by_exp, vip_level_thresholds


def extract_vip_value_from_inner(inner_result: Any) -> int:
    """从 getVipInfo 返回中提取 VIP 经验值（value 字段）。"""
    if not isinstance(inner_result, dict):
        raise RuntimeError("无法解析 VIP 业务返回 result（不是 object）")
    value = inner_result.get("value")
    if value is None:
        raise RuntimeError(f"VIP 返回缺少 value 字段: {inner_result}")
    try:
        return int(value)
    except (TypeError, ValueError) as e:
        raise RuntimeError(f"无法解析 VIP value: {value}") from e


def parse_vip_info_summary(user_id: str, inner_result: Any) -> dict[str, Any]:
    if not isinstance(inner_result, dict):
        raise RuntimeError("无法解析 VIP 业务返回 result（不是 object）")

    current_vip_exp = extract_vip_value_from_inner(inner_result)
    thresholds = vip_level_thresholds()
    api_level = inner_result.get("level")
    true_level = inner_result.get("trueLevel")
    try_level = inner_result.get("tryLevel")

    computed_level = level_by_exp(current_vip_exp, thresholds)
    vip_level = int(true_level if true_level is not None else api_level if api_level is not None else computed_level)

    next_lv = vip_level + 1 if (vip_level + 1) in thresholds else None
    next_threshold = thresholds.get(next_lv) if next_lv else None
    remaining = (next_threshold - current_vip_exp) if next_threshold is not None else None

    return {
        "userId": str(user_id),
        "currentVipExp": current_vip_exp,
        "vipLevel": vip_level,
        "trueLevel": true_level,
        "tryLevel": try_level,
        "nextVipLevelThreshold": next_threshold,
        "remainingToNextVipLevel": remaining,
    }
