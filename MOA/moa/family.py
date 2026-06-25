"""家族声望值结果解析。"""

from __future__ import annotations

from typing import Any

from .config import (
    family_fund_sub_rewards,
    family_fund_sub_tier_by_contribution,
    family_level_thresholds,
    level_by_exp,
)


def parse_family_exp_summary(family_id: str, inner_result: Any) -> dict[str, Any]:
    try:
        current_exp = int(float(inner_result))
    except (TypeError, ValueError) as e:
        raise RuntimeError(f"无法解析家族声望值: {inner_result}") from e
    thresholds = family_level_thresholds()
    lv = level_by_exp(current_exp, thresholds)
    next_lv = lv + 1 if (lv + 1) in thresholds else None
    next_threshold = thresholds.get(next_lv) if next_lv else None
    remaining = (next_threshold - current_exp) if next_threshold is not None else None
    return {
        "familyId": str(family_id),
        "currentFamilyExp": current_exp,
        "familyLevel": lv,
        "nextFamilyLevelThreshold": next_threshold,
        "remainingToNextFamilyLevel": remaining,
    }


def parse_family_fund_tier_set_count(inner_result: Any) -> int:
    try:
        return int(float(inner_result))
    except (TypeError, ValueError) as e:
        raise RuntimeError(f"无法解析家族基金档位设置结果: {inner_result}") from e


def parse_family_fund_summary(
    family_id: str,
    week_key: str,
    inner_result: Any,
    *,
    fund_tier: str | None = None,
) -> dict[str, Any]:
    try:
        total = float(inner_result)
    except (TypeError, ValueError) as e:
        raise RuntimeError(f"无法解析家族基金贡献值: {inner_result}") from e
    current_total = int(total) if total.is_integer() else total
    summary: dict[str, Any] = {
        "familyId": str(family_id),
        "weekKey": week_key,
        "currentFamilyFundTotal": current_total,
    }
    if fund_tier:
        sub_tier_info = family_fund_sub_tier_by_contribution(fund_tier, int(current_total))
        summary.update(sub_tier_info)
        next_sub = sub_tier_info["subTier"] + 1
        tiers = family_fund_sub_rewards(fund_tier)
        next_item = next((item for item in tiers if int(item.get("sub_tier", -1)) == next_sub), None)
        if next_item is not None:
            next_threshold = int(next_item.get("contribution", 0))
            summary["nextSubTier"] = next_sub
            summary["nextSubTierContributionThreshold"] = next_threshold
            summary["remainingToNextSubTier"] = next_threshold - int(current_total)
    return summary


def _normalize_member_user_id(item: Any) -> str | None:
    if item is None:
        return None
    if isinstance(item, (str, int)):
        uid = str(item).strip()
        return uid or None
    if isinstance(item, dict):
        for key in ("userId", "uid", "momoid", "id"):
            value = item.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return None


def parse_family_members_summary(family_id: str, inner_result: Any) -> dict[str, Any]:
    members: list[str] = []
    if isinstance(inner_result, list):
        for item in inner_result:
            uid = _normalize_member_user_id(item)
            if uid:
                members.append(uid)
    elif isinstance(inner_result, dict):
        raw_list = inner_result.get("list") or inner_result.get("members") or inner_result.get("userIds")
        if isinstance(raw_list, list):
            for item in raw_list:
                uid = _normalize_member_user_id(item)
                if uid:
                    members.append(uid)
        else:
            uid = _normalize_member_user_id(inner_result)
            if uid:
                members.append(uid)
    else:
        uid = _normalize_member_user_id(inner_result)
        if uid:
            members.append(uid)

    # 去重保序
    seen: set[str] = set()
    unique_members: list[str] = []
    for uid in members:
        if uid not in seen:
            seen.add(uid)
            unique_members.append(uid)

    return {
        "familyId": str(family_id),
        "memberCount": len(unique_members),
        "memberUserIds": unique_members,
    }


def _normalize_family_id(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int)):
        fid = str(value).strip()
        return fid or None
    if isinstance(value, dict):
        for key in ("familyId", "id", "family_id"):
            item = value.get(key)
            if item is not None and str(item).strip():
                return str(item).strip()
    return None


def parse_user_joined_family_summary(user_id: str, inner_result: Any) -> dict[str, Any]:
    family_id = _normalize_family_id(inner_result)
    if family_id is None and isinstance(inner_result, dict):
        family_id = _normalize_family_id(inner_result.get("familyInfo"))
    joined = family_id is not None and str(family_id).strip() not in ("", "0", "null")
    return {
        "userId": str(user_id).strip(),
        "joinedFamily": joined,
        "familyId": family_id if joined else None,
    }
