"""家族基金档位、奖池与成员应发钻测算（familyFundConfig）。"""

from __future__ import annotations

import asyncio
import math
from decimal import Decimal, ROUND_DOWN
from typing import Any

FAMILY_FUND_APP_KEY = "momo.bpm.biz.gameplatform.overseas-voga-mts-user"
FAMILY_FUND_NAMESPACE = "Application"
FAMILY_FUND_CONFIG_KEY = "familyFundConfig"

FAMILY_FUND_SHEET_ORDER = [
    "参数表",
    "家族基金测试",
]

# 单表：家族快照 + 贡献榜 + 应发钻测算 + 实发验收 + 测试结果总结
FAMILY_FUND_TEST_SHEET = "家族基金测试"
CALC_SHEET = FAMILY_FUND_TEST_SHEET

FAMILY_FUND_TEST_HEADER = [
    "周期",
    "家族ID",
    "家族名称",
    "上周总贡献",
    "本周档位",
    "本周总贡献",
    "奖池钻石",
    "userId",
    "手机号",
    "榜单排名",
    "成员贡献值",
    "达标",
    "分配比例",
    "应发钻石",
    "实际增量",
    "验收",
    "备注",
]

# 兼容旧引用
MEMBER_REWARD_HEADER = FAMILY_FUND_TEST_HEADER

LEGACY_SHEETS = (
    "家族快照",
    "贡献榜",
    "应发钻测算",
    "发钻实发验收",
    "测试结果",
)


def family_fund_workbook_title(week_monday: str) -> str:
    return f"{week_monday.strip()}家族基金数据测试"


async def rename_family_fund_workbook_async(workbook_url_or_id: str, week_monday: str) -> str:
    from alidocs_excel_export import rename_workbook_async  # noqa: PLC0415
    from mse_workbook_utils import node_id  # noqa: PLC0415

    title = family_fund_workbook_title(week_monday)
    workbook_id = node_id(workbook_url_or_id)
    await rename_workbook_async(workbook_id, title)
    return title


def rename_family_fund_workbook(workbook_url_or_id: str, week_monday: str) -> str:
    return asyncio.run(rename_family_fund_workbook_async(workbook_url_or_id, week_monday))


def fetch_family_fund_config() -> dict[str, Any]:
    from mse_config_export import _fetch_mse_config  # noqa: PLC0415

    fetched = _fetch_mse_config(
        namespace=FAMILY_FUND_NAMESPACE,
        config_key=FAMILY_FUND_CONFIG_KEY,
        app_key=FAMILY_FUND_APP_KEY,
    )
    return fetched["configValue"]


def load_family_fund_config_from_workbook(
    workbook: str,
    *,
    param_sheet: str | None = None,
) -> dict[str, Any]:
    from mse_param_sheet_to_json import _parse_param_sheet  # noqa: PLC0415
    from mse_workbook_utils import (  # noqa: PLC0415
        apply_parsed_values_to_original,
        fetch_workbook_sheets,
        resolve_param_sheet_name,
    )

    sheets = fetch_workbook_sheets(workbook)
    sheet_name = resolve_param_sheet_name(sheets, param_sheet)
    parsed, _ = _parse_param_sheet(sheets[sheet_name])
    original = fetch_family_fund_config()
    return apply_parsed_values_to_original(original, parsed)


def _apply_param_sheet_to_config(original: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    out = dict(original)
    base = parsed.get("基础") or {}
    for key, value in base.items():
        if value not in (None, ""):
            out[key] = value
    dispatch = parsed.get("发钻") or {}
    if dispatch:
        cfg = dict(out.get("diamondDispatchConfig") or {})
        for k, v in dispatch.items():
            if v not in (None, ""):
                cfg[k] = v
        out["diamondDispatchConfig"] = cfg
    return out


def tier_from_last_week_contribution(config: dict[str, Any], last_week_total: int) -> str:
    tiers = config.get("tiers") or []
    ordered = sorted(
        tiers,
        key=lambda t: int(t.get("minLastWeekContribution") or 0),
        reverse=True,
    )
    for item in ordered:
        if last_week_total >= int(item.get("minLastWeekContribution") or 0):
            return str(item.get("tierName") or "C").upper()
    return "C"


def pool_from_tier_contribution(config: dict[str, Any], tier: str, contribution: int) -> int:
    tier = str(tier).upper()
    sub_tiers = (config.get("tierSubTiers") or {}).get(tier) or []
    pool = 0
    for item in sub_tiers:
        threshold = int(item.get("thresholdContribution") or 0)
        if contribution >= threshold:
            pool = int(item.get("bonusDiamond") or 0)
    return pool


def _rank_group(config: dict[str, Any], rank: int) -> dict[str, Any] | None:
    for group in config.get("rankPrizes") or []:
        start = int(group.get("startRank") or 0)
        end = int(group.get("endRank") or start)
        if start <= rank <= end:
            return group
    return None


def _floor_pool_times_ratio(pool: int, ratio: float) -> int:
    """奖池 × 比例后舍去小数；用 Decimal 避免 27000*0.009 → 242.999… 的 float 误差。"""
    if ratio <= 0:
        return 0
    product = Decimal(pool) * Decimal(str(ratio))
    return int(product.to_integral_value(rounding=ROUND_DOWN))


def rank_share_ratio(config: dict[str, Any], rank: int) -> float:
    group = _rank_group(config, rank)
    if not group:
        return 0.0
    ratio_map = group.get("rewardRatioMap") or {}
    if ratio_map:
        inner = ratio_map.get(str(rank))
        if inner is None:
            return 0.0
        combined = Decimal(str(group.get("ratio") or 0)) * Decimal(str(inner))
        return float(combined)
    return float(group.get("ratio") or 0)


def after_top_share_ratio(config: dict[str, Any], after_top_count: int) -> float:
    if after_top_count <= 0:
        return 0.0
    if after_top_count <= 15:
        return 0.00325
    total = Decimal(str(config.get("afterTopRankRatio") or "0.05"))
    return float(total / Decimal(after_top_count))


def _is_after_top_rank(rank: Any) -> bool:
    if rank is None:
        return True
    try:
        return int(rank) > 30
    except (TypeError, ValueError):
        return True


def compute_member_expected_diamonds(
    *,
    config: dict[str, Any],
    pool: int,
    members: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """members: {userId, rank, contribution}；rank None 或 >30 视为 30+ 榜外均分。"""
    min_rank = int(config.get("minContributionToRank") or 500)

    after_top = [
        m for m in members
        if int(m.get("contribution") or 0) >= min_rank and _is_after_top_rank(m.get("rank"))
    ]
    after_ratio = after_top_share_ratio(config, len(after_top))

    rows: list[dict[str, Any]] = []
    for m in members:
        uid = str(m.get("userId") or "")
        contrib = int(m.get("contribution") or 0)
        rank = m.get("rank")
        eligible = contrib >= min_rank
        ratio = 0.0
        if rank is not None and int(rank) <= 30 and eligible:
            ratio = rank_share_ratio(config, int(rank))
        elif eligible and _is_after_top_rank(rank):
            ratio = after_ratio
        expected = _floor_pool_times_ratio(pool, ratio) if eligible and ratio > 0 else 0
        rows.append(
            {
                "userId": uid,
                "rank": rank,
                "contribution": contrib,
                "eligible": eligible,
                "shareRatio": ratio,
                "expectedDiamond": expected,
            }
        )
    return rows
