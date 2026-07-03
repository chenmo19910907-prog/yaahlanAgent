"""家族 PK 档位达标与奖池贡献计算（rebateRatio 版）。"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from mse_workbook_utils import format_rank_range


def family_pk_workbook_title(pk_date: str) -> str:
    """家族 PK 钉钉表文档名：{匹配日期}家族PK数据测试。"""
    return f"{pk_date.strip()}家族PK数据测试"


async def rename_family_pk_workbook_async(workbook_url_or_id: str, pk_date: str) -> str:
    from alidocs_excel_export import rename_workbook_async  # noqa: PLC0415
    from mse_workbook_utils import node_id  # noqa: PLC0415

    title = family_pk_workbook_title(pk_date)
    workbook_id = node_id(workbook_url_or_id)
    await rename_workbook_async(workbook_id, title)
    return title


def rename_family_pk_workbook(workbook_url_or_id: str, pk_date: str) -> str:
    return asyncio.run(rename_family_pk_workbook_async(workbook_url_or_id, pk_date))


def load_family_pk_config_from_workbook(
    workbook: str,
    *,
    param_sheet: str | None = None,
) -> dict[str, Any]:
    """从钉钉参数表读取 familyPkConfig（minWinPk / minRewardPk 等），合并 MSE 原始结构。"""
    from mse_config_export import _fetch_mse_config  # noqa: PLC0415
    from mse_param_sheet_to_json import _parse_param_sheet  # noqa: PLC0415
    from mse_workbook_utils import (  # noqa: PLC0415
        apply_parsed_values_to_original,
        fetch_workbook_sheets,
        resolve_param_sheet_name,
    )

    sheets = fetch_workbook_sheets(workbook)
    sheet_name = resolve_param_sheet_name(sheets, param_sheet)
    parsed, _ = _parse_param_sheet(sheets[sheet_name])
    original = _fetch_mse_config(namespace="voga-common", config_key="familyPkConfig")["configValue"]
    config = apply_parsed_values_to_original(original, parsed)
    for key in ("minWinPk", "minRewardPk"):
        if config.get(key) is None:
            raise RuntimeError(f"参数表缺少 {key}（获胜最低 PK / 领奖最低 PK）")
    return config


def bracket_for_rank(rank: int | None, brackets: list[dict[str, Any]]) -> dict[str, Any]:
    if not brackets:
        raise ValueError("bracketGradients 为空")
    if rank is None:
        return brackets[-1]
    for bracket in brackets:
        start = int(bracket["rankStart"])
        end = bracket.get("rankEnd")
        if end is None:
            if rank >= start:
                return bracket
        elif start <= rank <= int(end):
            return bracket
    return brackets[-1]


def bracket_label_for_rank(rank: int | None, brackets: list[dict[str, Any]]) -> str:
    bracket = bracket_for_rank(rank, brackets)
    return format_rank_range(bracket.get("rankStart"), bracket.get("rankEnd"))


def compute_bracket_daily_avgs(
    rank_map: dict[str, dict[str, Any]],
    brackets: list[dict[str, Any]],
) -> dict[str, float]:
    """区间内家族收礼均值：同名次区间所有家族 receiveScore 的算术平均。"""
    scores_by_label: dict[str, list[int]] = defaultdict(list)
    for item in rank_map.values():
        rank = item.get("rank")
        if rank is None:
            continue
        label = bracket_label_for_rank(int(rank), brackets)
        scores_by_label[label].append(int(item.get("receiveScore") or 0))
    return {
        label: (sum(scores) / len(scores) if scores else 0.0)
        for label, scores in scores_by_label.items()
    }


def min_daily_avg_from_config(config: dict[str, Any]) -> float:
    """日均兜底：MSE 键 minDailyAvg；兼容旧键 minBracketDailyAvg。"""
    if config.get("minDailyAvg") is not None:
        return float(config["minDailyAvg"])
    if config.get("minBracketDailyAvg") is not None:
        return float(config["minBracketDailyAvg"])
    raise RuntimeError("配置缺少 minDailyAvg（日均兜底）")


def effective_daily_avg(daily_avg: float, min_daily_avg: float) -> float:
    return max(daily_avg, min_daily_avg)


def tier_threshold_pk(effective_avg: float, coefficient: float) -> int:
    return int(effective_avg * float(coefficient))


def tier_diamond_reward(threshold_pk: int, rebate_ratio: float) -> int:
    return int(threshold_pk * float(rebate_ratio))


def rebate_value(gradient: dict[str, Any]) -> float:
    rebate = gradient.get("rebateRatio")
    if rebate is None and gradient.get("bonusDiamond") is not None:
        return float(gradient["bonusDiamond"])
    if rebate is None:
        return 0.0
    return float(rebate)


def calc_family_tier_rows(
    *,
    pk_date: str,
    rank_date: str,
    family_id: str,
    family_name: str,
    rank: int | None,
    receive_score: int,
    member_count: int,
    bracket_label: str,
    bracket: dict[str, Any],
    bracket_daily_avg: float,
    min_bracket_daily_avg: float,
) -> list[list[Any]]:
    effective = effective_daily_avg(bracket_daily_avg, min_bracket_daily_avg)
    rows: list[list[Any]] = []
    for tier_idx, gradient in enumerate(bracket.get("gradients") or [], start=1):
        coeff = gradient.get("coefficient")
        rebate = rebate_value(gradient)
        threshold = tier_threshold_pk(effective, float(coeff or 0))
        diamond = tier_diamond_reward(threshold, rebate)
        rows.append(
            [
                pk_date,
                rank_date,
                family_id,
                family_name,
                "" if rank is None else str(rank),
                str(receive_score),
                str(member_count),
                bracket_label,
                round(bracket_daily_avg, 2),
                round(effective, 2),
                tier_idx,
                coeff,
                threshold,
                rebate,
                diamond,
            ]
        )
    return rows


def family_pool_from_tier_sheet(
    family_id: str,
    family_pk: int,
    family_tiers: dict[str, list[dict[str, Any]]],
    *,
    base_pool_diamond: int = 999,
) -> int:
    """按家族 PK 在档位表中取可达最高档的档位钻石；未达任何档则用 basePoolDiamond。"""
    best = 0
    reached = False
    for tier in family_tiers.get(family_id, []):
        threshold = int(tier.get("thresholdPk") or 0)
        diamond = int(tier.get("tierDiamond") or 0)
        if family_pk >= threshold:
            best = diamond
            reached = True
    return best if reached else int(base_pool_diamond)


def pool_for_battle_from_tier_sheet(
    family_a: str,
    family_b: str | None,
    *,
    family_pk: dict[str, int],
    family_tiers: dict[str, list[dict[str, Any]]],
    base_pool_diamond: int = 999,
) -> int:
    contrib_a = family_pool_from_tier_sheet(
        family_a,
        family_pk.get(family_a, 0),
        family_tiers,
        base_pool_diamond=base_pool_diamond,
    )
    if family_b:
        contrib_b = family_pool_from_tier_sheet(
            family_b,
            family_pk.get(family_b, 0),
            family_tiers,
            base_pool_diamond=base_pool_diamond,
        )
        return contrib_a + contrib_b
    return contrib_a * 2


def family_pool_contribution(
    family_pk: int,
    *,
    bracket: dict[str, Any],
    bracket_daily_avg: float,
    min_bracket_daily_avg: float,
) -> int:
    """家族奖池贡献：家族 PK 达到的最高档位钻石。"""
    effective = effective_daily_avg(bracket_daily_avg, min_bracket_daily_avg)
    best = 0
    for gradient in bracket.get("gradients") or []:
        coeff = float(gradient.get("coefficient") or 0)
        threshold = tier_threshold_pk(effective, coeff)
        if family_pk >= threshold:
            best = tier_diamond_reward(threshold, rebate_value(gradient))
    return best


def pool_for_battle(
    family_a: str,
    family_b: str | None,
    *,
    family_pk: dict[str, int],
    rank_map: dict[str, dict[str, Any]],
    brackets: list[dict[str, Any]],
    bracket_daily_avgs: dict[str, float],
    min_bracket_daily_avg: float,
) -> int:
    def _contrib(fid: str) -> int:
        rank = rank_map.get(fid, {}).get("rank")
        rank_int = int(rank) if rank is not None else None
        bracket = bracket_for_rank(rank_int, brackets)
        label = bracket_label_for_rank(rank_int, brackets)
        daily_avg = bracket_daily_avgs.get(label, 0.0)
        return family_pool_contribution(
            family_pk.get(fid, 0),
            bracket=bracket,
            bracket_daily_avg=daily_avg,
            min_bracket_daily_avg=min_bracket_daily_avg,
        )

    if family_b:
        return _contrib(family_a) + _contrib(family_b)
    return _contrib(family_a) * 2


def compute_member_expected_diamonds(
    *,
    battles: list[dict[str, Any]],
    bye_families: list[str],
    member_pk: dict[tuple[str, str], int],
    family_pk: dict[str, int],
    family_tiers: dict[str, list[dict[str, Any]]],
    config: dict[str, Any],
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """按匹配胜负与 PK 门槛计算各成员应得钻石；奖池来自档位表。"""
    min_win = int(config["minWinPk"])
    min_reward = int(config["minRewardPk"])
    max_user = int(config.get("maxRewardDiamondPerUser", 100000))
    base_pool_diamond = int(config.get("basePoolDiamond", 999))

    expected: dict[str, int] = defaultdict(int)
    member_rows: list[dict[str, Any]] = []

    def _battle_pool(fa: str, fb: str | None) -> int:
        return pool_for_battle_from_tier_sheet(
            fa,
            fb,
            family_pk=family_pk,
            family_tiers=family_tiers,
            base_pool_diamond=base_pool_diamond,
        )

    def _append_members(
        winner: str,
        pool: int,
        *,
        result: str,
        scenario: str,
        opponent: str | None,
        opponent_pk: int,
        note: str,
    ) -> None:
        wpk = family_pk.get(winner, 0)
        for (fid, uid), mpk in member_pk.items():
            if fid != winner:
                continue
            if pool <= 0 or wpk <= 0 or result != "胜":
                reward = 0
                skip = note if result != "胜" else "无奖池"
            elif mpk < min_reward:
                reward = 0
                skip = f"用户PK<{min_reward}"
            else:
                reward = min((mpk * pool) // wpk, max_user)
                skip = ""
            if reward > 0:
                expected[uid] += reward
            member_rows.append(
                {
                    "familyId": fid,
                    "userId": uid,
                    "memberPk": mpk,
                    "familyPk": wpk,
                    "opponentFamilyId": opponent or "",
                    "opponentFamilyPk": opponent_pk,
                    "matchResult": result,
                    "scenario": scenario,
                    "poolDiamond": pool,
                    "minRewardPk": min_reward,
                    "expectedDiamond": reward,
                    "note": skip or note,
                }
            )

    def _append_losers(
        loser: str,
        winner: str,
        *,
        scenario: str,
        pool: int,
        winner_pk: int,
        loser_pk: int,
        result: str,
        note: str,
    ) -> None:
        for (fid, uid), mpk in member_pk.items():
            if fid != loser:
                continue
            member_rows.append(
                {
                    "familyId": fid,
                    "userId": uid,
                    "memberPk": mpk,
                    "familyPk": loser_pk,
                    "opponentFamilyId": winner,
                    "opponentFamilyPk": winner_pk,
                    "matchResult": result,
                    "scenario": scenario,
                    "poolDiamond": pool,
                    "minRewardPk": min_reward,
                    "expectedDiamond": 0,
                    "note": note,
                }
            )

    for battle in battles:
        fa = battle["familyA"]
        fb = battle["familyB"]
        fapk = family_pk.get(fa, 0)
        fbpk = family_pk.get(fb, 0)
        scenario = infer_battle_scenario(
            fa,
            fb,
            family_pk=family_pk,
            member_pk=member_pk,
            min_win=min_win,
            min_reward=min_reward,
        )
        pool = _battle_pool(fa, fb)

        if fapk == fbpk:
            note = "双方PK相同，平局无发钻"
            for fid, pk, opp, oppk in ((fa, fapk, fb, fbpk), (fb, fbpk, fa, fapk)):
                for (mfid, uid), mpk in member_pk.items():
                    if mfid != fid:
                        continue
                    member_rows.append(
                        {
                            "familyId": fid,
                            "userId": uid,
                            "memberPk": mpk,
                            "familyPk": pk,
                            "opponentFamilyId": opp,
                            "opponentFamilyPk": oppk,
                            "matchResult": "平",
                            "scenario": "tie",
                            "poolDiamond": pool,
                            "minRewardPk": min_reward,
                            "expectedDiamond": 0,
                            "note": note,
                        }
                    )
            continue

        if fapk > fbpk:
            winner, loser = fa, fb
            winner_pk, loser_pk = fapk, fbpk
        else:
            winner, loser = fb, fa
            winner_pk, loser_pk = fbpk, fapk

        if winner_pk < min_win:
            note = f"获胜方家族PK<{min_win}，按平局处理"
            for fid, pk, opp, oppk in (
                (fa, fapk, fb, fbpk),
                (fb, fbpk, fa, fapk),
            ):
                for (mfid, uid), mpk in member_pk.items():
                    if mfid != fid:
                        continue
                    member_rows.append(
                        {
                            "familyId": fid,
                            "userId": uid,
                            "memberPk": mpk,
                            "familyPk": pk,
                            "opponentFamilyId": opp,
                            "opponentFamilyPk": oppk,
                            "matchResult": "平",
                            "scenario": "pk_low",
                            "poolDiamond": pool,
                            "minRewardPk": min_reward,
                            "expectedDiamond": 0,
                            "note": note,
                        }
                    )
            continue

        _append_members(
            winner,
            pool,
            result="胜",
            scenario=scenario,
            opponent=loser,
            opponent_pk=loser_pk,
            note="按家族PK占比瓜分奖池",
        )
        _append_losers(
            loser,
            winner,
            scenario="lose",
            pool=pool,
            winner_pk=winner_pk,
            loser_pk=loser_pk,
            result="负",
            note="失败方无发钻",
        )

    for idx, fa in enumerate(bye_families):
        scenario = "bye_win" if idx % 2 == 0 else "bye_pk_low"
        fapk = family_pk.get(fa, 0)
        pool = _battle_pool(fa, None)
        if fapk >= min_win:
            _append_members(
                fa,
                pool,
                result="胜",
                scenario=scenario,
                opponent=None,
                opponent_pk=0,
                note="轮空且家族PK达标",
            )
        else:
            for (fid, uid), mpk in member_pk.items():
                if fid != fa:
                    continue
                member_rows.append(
                    {
                        "familyId": fid,
                        "userId": uid,
                        "memberPk": mpk,
                        "familyPk": fapk,
                        "opponentFamilyId": "",
                        "opponentFamilyPk": 0,
                        "matchResult": "平",
                        "scenario": scenario,
                        "poolDiamond": pool,
                        "minRewardPk": min_reward,
                        "expectedDiamond": 0,
                        "note": f"轮空但家族PK<{min_win}",
                    }
                )

    return dict(expected), member_rows


def infer_battle_scenario(
    fa: str,
    fb: str,
    *,
    family_pk: dict[str, int],
    member_pk: dict[tuple[str, str], int],
    min_win: int,
    min_reward: int,
) -> str:
    """按当前家族/成员 PK 推断对战场景（不依赖造数 battlePlans）。"""
    fapk = family_pk.get(fa, 0)
    fbpk = family_pk.get(fb, 0)
    if fapk == fbpk:
        return "tie"
    if max(fapk, fbpk) < min_win:
        return "pk_low"
    winner = fa if fapk > fbpk else fb
    if any(
        0 < member_pk.get((winner, uid), 0) < min_reward
        for (fid, uid) in member_pk
        if fid == winner
    ):
        return "member_low"
    return "win"


def _sheet_int(value: Any) -> int:
    try:
        return int(str(value or "").strip() or 0)
    except (TypeError, ValueError):
        return 0


def sort_match_verify_detail_rows(rows: list[list[Any]]) -> list[list[Any]]:
    """匹配验收：按双方收礼值总和降序。"""

    def sort_key(row: list[Any]) -> tuple[int, str]:
        receive_total = _sheet_int(row[5] if len(row) > 5 else 0) + _sheet_int(
            row[7] if len(row) > 7 else 0
        )
        return (-receive_total, str(row[0] if row else ""))

    return sorted(rows, key=sort_key)


def sort_member_reward_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """用户发钻测试：按匹配双方家族 PK 总值降序；同家族内成员按用户 PK 值降序。"""

    def sort_key(item: dict[str, Any]) -> tuple[int, str, int, str]:
        pk_total = int(item.get("familyPk") or 0) + int(item.get("opponentFamilyPk") or 0)
        member_pk = int(item.get("memberPk") or 0)
        return (
            -pk_total,
            str(item.get("familyId") or ""),
            -member_pk,
            str(item.get("userId") or ""),
        )

    return sorted(rows, key=sort_key)
