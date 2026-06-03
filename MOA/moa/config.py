"""配置加载与等级阈值计算。"""

from __future__ import annotations

import json
import os
from typing import Any

from .paths import thresholds_path

_DEFAULT_CONFIG: dict[str, Any] = {
    "room_level_exp_thresholds": {
        "1": 0,
        "2": 200000,
        "3": 1000000,
        "4": 4500000,
        "5": 18000000,
        "6": 63000000,
        "7": 189000000,
    }
}

_CONFIG_CACHE: dict[str, Any] | None = None
_ROOM_THRESHOLDS: dict[int, int] | None = None
_VIP_THRESHOLDS: dict[int, int] | None = None
_MEMBER_LV_THRESHOLDS: dict[int, int] | None = None
_NOBLE_THRESHOLDS: dict[int, int] | None = None
_FAMILY_THRESHOLDS: dict[int, int] | None = None
_FAMILY_FUND_SUB_REWARDS: dict[str, list[dict[str, Any]]] | None = None


def _base_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config() -> dict[str, Any]:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    cfg_path = thresholds_path()
    legacy_path = os.path.join(_base_dir(), "config.json")
    if not os.path.exists(cfg_path) and os.path.exists(legacy_path):
        cfg_path = legacy_path
    cfg = dict(_DEFAULT_CONFIG)
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except (OSError, json.JSONDecodeError):
            cfg = dict(_DEFAULT_CONFIG)

    _CONFIG_CACHE = cfg
    return cfg


def _parse_thresholds(raw_key: str, label: str) -> dict[int, int]:
    raw = load_config().get(raw_key)
    if not isinstance(raw, dict):
        raise RuntimeError(f"配置错误：{raw_key} 必须是 object")
    thresholds: dict[int, int] = {}
    for k, v in raw.items():
        try:
            thresholds[int(k)] = int(v)
        except (TypeError, ValueError) as e:
            raise RuntimeError(f"配置错误：{raw_key} 键值必须可转为 int: {k}={v}") from e
    if not thresholds:
        raise RuntimeError(f"配置错误：{raw_key} 不能为空")
    return thresholds


def room_level_thresholds() -> dict[int, int]:
    global _ROOM_THRESHOLDS
    if _ROOM_THRESHOLDS is None:
        _ROOM_THRESHOLDS = _parse_thresholds("room_level_exp_thresholds", "房间")
    return _ROOM_THRESHOLDS


def vip_level_thresholds() -> dict[int, int]:
    global _VIP_THRESHOLDS
    if _VIP_THRESHOLDS is None:
        _VIP_THRESHOLDS = _parse_thresholds("vip_level_exp_thresholds", "VIP")
    return _VIP_THRESHOLDS


def member_level_thresholds() -> dict[int, int]:
    global _MEMBER_LV_THRESHOLDS
    if _MEMBER_LV_THRESHOLDS is None:
        _MEMBER_LV_THRESHOLDS = _parse_thresholds("member_level_exp_thresholds", "房间成员")
    return _MEMBER_LV_THRESHOLDS


def noble_level_thresholds() -> dict[int, int]:
    global _NOBLE_THRESHOLDS
    if _NOBLE_THRESHOLDS is None:
        _NOBLE_THRESHOLDS = _parse_thresholds("noble_level_exp_thresholds", "贵族")
    return _NOBLE_THRESHOLDS


def family_level_thresholds() -> dict[int, int]:
    global _FAMILY_THRESHOLDS
    if _FAMILY_THRESHOLDS is None:
        _FAMILY_THRESHOLDS = _parse_thresholds("family_level_exp_thresholds", "家族")
    return _FAMILY_THRESHOLDS


def family_fund_sub_rewards(tier: str) -> list[dict[str, Any]]:
    global _FAMILY_FUND_SUB_REWARDS
    if _FAMILY_FUND_SUB_REWARDS is None:
        raw = load_config().get("family_fund_tier_sub_rewards")
        if not isinstance(raw, dict):
            raise ValueError("config.json 缺少 family_fund_tier_sub_rewards")
        parsed: dict[str, list[dict[str, Any]]] = {}
        for key, items in raw.items():
            if not isinstance(items, list):
                raise ValueError(f"family_fund_tier_sub_rewards.{key} 必须是数组")
            parsed[str(key).upper()] = [item for item in items if isinstance(item, dict)]
        _FAMILY_FUND_SUB_REWARDS = parsed
    tier = str(tier).strip().upper()
    if tier not in _FAMILY_FUND_SUB_REWARDS:
        raise ValueError(f"不支持的家族基金档位: {tier}，支持: {sorted(_FAMILY_FUND_SUB_REWARDS)}")
    return _FAMILY_FUND_SUB_REWARDS[tier]


def family_fund_sub_tier_by_contribution(tier: str, contribution: int) -> dict[str, Any]:
    if contribution < 0:
        raise ValueError("contribution 不能为负数")
    tiers = family_fund_sub_rewards(tier)
    current = tiers[0]
    for item in tiers:
        threshold = int(item.get("contribution", 0))
        if contribution >= threshold:
            current = item
        else:
            break
    return {
        "fundTier": str(tier).upper(),
        "subTier": int(current.get("sub_tier", 0)),
        "contributionThreshold": int(current.get("contribution", 0)),
        "rewardDiamonds": int(current.get("reward_diamonds", 0)),
    }


def build_family_fund_contrib_delta_for_sub_tier(tier: str, sub_tier: int, current_contribution: int) -> int:
    tiers = family_fund_sub_rewards(tier)
    target = next((item for item in tiers if int(item.get("sub_tier", -1)) == sub_tier), None)
    if target is None:
        supported = [int(item.get("sub_tier", 0)) for item in tiers]
        raise ValueError(f"不支持的家族基金小档位: {sub_tier}，支持: {supported}")
    if current_contribution < 0:
        raise ValueError("current_contribution 不能为负数")
    threshold = int(target.get("contribution", 0))
    delta = threshold - current_contribution
    if delta <= 0:
        raise ValueError(
            f"当前贡献值已 >= 目标小档位阈值：current={current_contribution}, target={threshold}"
        )
    return delta


def level_by_exp(exp: int, thresholds: dict[int, int]) -> int:
    if exp < 0:
        raise ValueError("exp 不能为负数")
    level = min(thresholds)
    for lv in sorted(thresholds):
        if exp >= thresholds[lv]:
            level = lv
    return level


def normalize_level_exp_mode(mode: str | None) -> str:
    value = (mode or "min").strip().lower()
    if value not in {"min", "max"}:
        raise ValueError(f"level_exp_mode 仅支持 min/max，当前: {mode}")
    return value


def target_exp_for_level(level: int, thresholds: dict[int, int], mode: str = "min") -> int:
    """按等级计算目标经验值。

    - min：该等级最低阈值（刚达到该等级）
    - max：该等级最高经验（下一等级阈值 - 1；最高等级时同 min）
    """
    normalized_mode = normalize_level_exp_mode(mode)
    if level not in thresholds:
        raise ValueError(f"不支持的等级: {level}，支持范围: {sorted(thresholds)}")

    if normalized_mode == "min":
        return thresholds[level]

    sorted_levels = sorted(thresholds)
    index = sorted_levels.index(level)
    if index + 1 < len(sorted_levels):
        return thresholds[sorted_levels[index + 1]] - 1
    return thresholds[level]


def build_exp_delta_for_level(
    level: int,
    current_exp: int,
    thresholds: dict[int, int],
    label: str,
    mode: str = "min",
) -> int:
    if current_exp < 0:
        raise ValueError("current_exp 不能为负数")
    normalized_mode = normalize_level_exp_mode(mode)
    target = target_exp_for_level(level, thresholds, normalized_mode)
    delta = target - current_exp
    if delta <= 0:
        mode_label = "最低" if normalized_mode == "min" else "最高"
        raise ValueError(
            f"当前经验值已 >= 目标{label}等级 {level} 的{mode_label}阈值："
            f"current_exp={current_exp}, target={target}"
        )
    return delta


def describe_level_upgrade_plan(
    *,
    level: int,
    current_exp: int,
    thresholds: dict[int, int],
    label: str,
    mode: str = "min",
) -> tuple[int, int, str]:
    normalized_mode = normalize_level_exp_mode(mode)
    target = target_exp_for_level(level, thresholds, normalized_mode)
    delta = build_exp_delta_for_level(level, current_exp, thresholds, label, normalized_mode)
    mode_label = "最低" if normalized_mode == "min" else "最高"
    message = (
        f"目标{label}等级: {level}（{mode_label}阈值 {target}），"
        f"当前经验值: {current_exp}，需要增加: {delta}"
    )
    return delta, target, message


def build_room_exp_delta_for_level(level: int, current_exp: int, mode: str = "min") -> int:
    return build_exp_delta_for_level(level, current_exp, room_level_thresholds(), "房间", mode)


def build_vip_exp_delta_for_level(level: int, current_exp: int, mode: str = "min") -> int:
    return build_exp_delta_for_level(level, current_exp, vip_level_thresholds(), " VIP", mode)


def build_member_lv_exp_delta_for_level(level: int, current_exp: int, mode: str = "min") -> int:
    return build_exp_delta_for_level(level, current_exp, member_level_thresholds(), "房间成员", mode)


def build_noble_exp_delta_for_level(level: int, current_exp: int, mode: str = "min") -> int:
    return build_exp_delta_for_level(level, current_exp, noble_level_thresholds(), "贵族", mode)


def build_family_exp_delta_for_level(level: int, current_exp: int, mode: str = "min") -> int:
    return build_exp_delta_for_level(level, current_exp, family_level_thresholds(), "家族", mode)


def build_room_exp_expr(room_id: str, exp: int) -> str:
    room_id = str(room_id).strip()
    if not room_id:
        raise ValueError("room_id 不能为空")
    if exp < 0:
        raise ValueError("exp 不能为负数")
    return f'context.getBean("roomProfileDao").addRoomActiveValue("{room_id}",{exp}D)'


def build_family_fund_contrib_expr(family_id: str, contrib: int, week_key: str) -> str:
    family_id = str(family_id).strip()
    if not family_id:
        raise ValueError("family_id 不能为空")
    if contrib < 0:
        raise ValueError("family_fund_contrib 不能为负数")
    week_key = str(week_key).strip()
    if not week_key.endswith("-week"):
        raise ValueError(f"week_key 格式无效: {week_key}，应为 YYYYMMDD-week")
    return (
        f'context.getBean("familyFundDao").incrFundFamilyTotal("{family_id}",{contrib}L,"{week_key}")'
    )


def build_family_fund_clear_expr(family_id: str, week_offset: int) -> str:
    family_id = str(family_id).strip()
    if not family_id:
        raise ValueError("family_id 不能为空")
    if week_offset > 0:
        raise ValueError("family_fund_week_offset 不能为正数（0=本周，-1=上周）")
    return f'context.getBean("familyFundService").delFamilyFundRankTest("{family_id}",{week_offset})'


def build_family_fund_tier_set_expr(family_ids: list[str], tier: str, flag: int = 0) -> str:
    ids = [str(item).strip() for item in family_ids if str(item).strip()]
    if not ids:
        raise ValueError("family_ids 不能为空")
    tier = str(tier).strip().upper()
    if tier not in {"A", "B", "C"}:
        raise ValueError(f"family_fund_tier 无效: {tier}")
    if flag < 0:
        raise ValueError("family_fund_tier_flag 不能为负数")
    ids_literal = ",".join(f'"{item}"' for item in ids)
    return (
        "context.getBean(\"familyFundService\").batchSetFamilyFundTierForTest("
        f'java.util.Arrays.asList(new String[]{{{ids_literal}}}),"{tier}",{flag})'
    )


def family_fund_plan_by_reward_diamonds(reward_diamonds: int) -> dict[str, Any]:
    if reward_diamonds <= 0:
        raise ValueError("reward_diamonds 必须为正整数")
    matches: list[dict[str, Any]] = []
    for tier in ("A", "B", "C"):
        for item in family_fund_sub_rewards(tier):
            diamonds = int(item.get("reward_diamonds", 0))
            if diamonds != reward_diamonds:
                continue
            matches.append(
                {
                    "fundTier": tier,
                    "subTier": int(item.get("sub_tier", 0)),
                    "contribution": int(item.get("contribution", 0)),
                    "rewardDiamonds": diamonds,
                }
            )
    if not matches:
        raise ValueError(f"未找到返奖钻石 {reward_diamonds} 对应的档位配置")
    if len(matches) > 1:
        brief = ", ".join(
            f"{m['fundTier']}/档位{m['subTier']}/贡献{m['contribution']}" for m in matches
        )
        raise ValueError(f"返奖钻石 {reward_diamonds} 对应多个档位，请指定 tier：{brief}")
    return matches[0]


def section_defaults(section: str, fallback: dict[str, Any]) -> dict[str, Any]:
    raw = load_config().get(section)
    if not isinstance(raw, dict):
        return fallback
    merged = dict(fallback)
    merged.update(raw)
    return merged
