"""家族基金 MOA 查询：家族总贡献、成员贡献、档位推导。"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

from repo_paths import moa_execute_path, moa_template  # noqa: E402

_CONTRIB_TPL = moa_template("家族-增加基金贡献值.json")
_MEMBERS_TPL = moa_template("家族-查询成员userId.json")


def normalize_week_monday(text: str) -> str:
    value = text.strip()
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return value
    raise ValueError(f"week_monday 须为 yyyy-MM-dd: {text!r}")


def week_key_from_monday(week_monday: str) -> str:
    week_monday = normalize_week_monday(week_monday)
    return datetime.strptime(week_monday, "%Y-%m-%d").strftime("%Y%m%d") + "-week"


def prev_week_monday(week_monday: str) -> str:
    week_monday = normalize_week_monday(week_monday)
    prev = datetime.strptime(week_monday, "%Y-%m-%d").date() - timedelta(days=7)
    return prev.strftime("%Y-%m-%d")


def week_monday_for_dispatch_offset(week_monday: str, dispatch_offset: int) -> str:
    week_monday = normalize_week_monday(week_monday)
    if dispatch_offset == 0:
        return week_monday
    if dispatch_offset == -1:
        return prev_week_monday(week_monday)
    raise ValueError(f"dispatch_offset 无效: {dispatch_offset}（仅支持 0 或 -1）")


def _parse_json_stdout(text: str) -> Any:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError(f"未解析到 JSON: {text[:300]}")
    return json.loads(text[start : end + 1])


def _run_moa(extra: list[str], *, timeout_s: int = 60) -> Any:
    proc = subprocess.run(
        [sys.executable, str(moa_execute_path()), *extra],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "MOA 失败")[-500:])
    return _parse_json_stdout(proc.stdout)


def query_family_fund_total(family_id: str, week_key: str) -> int:
    week_monday = week_key.replace("-week", "")
    if len(week_monday) == 8:
        week_monday = f"{week_monday[:4]}-{week_monday[4:6]}-{week_monday[6:8]}"
    data = _run_moa(
        [
            "--payload-file",
            str(_CONTRIB_TPL),
            "--family-id",
            str(family_id),
            "--family-fund-contrib",
            "0",
            "--family-fund-week",
            week_monday,
        ]
    )
    return int(data["currentFamilyFundTotal"])


def query_member_fund_contribution(family_id: str, user_id: str, week_key: str) -> int:
    expr = (
        f'context.getBean("familyFundDao").incrFundContribution('
        f'"{family_id}","{user_id}",0L,"{week_key}")'
    )
    resp = _run_moa(["--payload-file", str(_CONTRIB_TPL), "--expr", expr])
    inner = resp.get("result", {}).get("result", resp)
    if isinstance(inner, dict):
        raise RuntimeError(f"成员贡献查询异常: {inner}")
    value = float(inner)
    return int(value) if value.is_integer() else int(value)


def query_family_members(family_id: str) -> list[str]:
    data = _run_moa(
        [
            "--payload-file",
            str(_MEMBERS_TPL),
            "--family-id",
            str(family_id),
            "--family-query-members",
        ]
    )
    ids = data.get("memberUserIds") or []
    return [str(uid) for uid in ids if str(uid).isdigit()]


def assign_contribution_ranks(
    rows: list[dict[str, Any]],
    *,
    min_contribution_to_rank: int = 500,
) -> None:
    """贡献倒序；贡献相同按 userId 倒序（与服务端发奖榜单一致）。"""
    for row in rows:
        row["rank"] = None
    eligible = [r for r in rows if int(r.get("contribution") or 0) >= min_contribution_to_rank]
    eligible.sort(key=lambda r: (-int(r["contribution"]), -int(r["userId"])))
    for index, row in enumerate(eligible, start=1):
        row["rank"] = index if index <= 30 else None


def build_member_rank_list(
    *,
    family_id: str,
    week_key: str,
    min_contribution_to_rank: int = 500,
    member_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    members = member_ids or query_family_members(family_id)
    rows: list[dict[str, Any]] = []
    for uid in members:
        contrib = query_member_fund_contribution(family_id, uid, week_key)
        rows.append({"userId": uid, "contribution": contrib, "rank": None})
    assign_contribution_ranks(rows, min_contribution_to_rank=min_contribution_to_rank)
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 9999, -r["contribution"], -int(r["userId"])))
    return rows


def build_family_fund_snapshot(
    *,
    family_id: str,
    week_monday: str,
    config: dict[str, Any],
    admin_family_name: str = "",
) -> dict[str, Any]:
    from family_fund_calc_utils import (  # noqa: PLC0415
        pool_from_tier_contribution,
        tier_from_last_week_contribution,
    )

    week_key = week_key_from_monday(week_monday)
    last_week_key = week_key_from_monday(prev_week_monday(week_monday))
    current_total = query_family_fund_total(family_id, week_key)
    last_week_total = query_family_fund_total(family_id, last_week_key)
    tier = tier_from_last_week_contribution(config, last_week_total)
    pool = pool_from_tier_contribution(config, tier, current_total)
    return {
        "familyId": str(family_id),
        "familyName": admin_family_name,
        "weekMonday": week_monday,
        "weekKey": week_key,
        "lastWeekKey": last_week_key,
        "lastWeekTotalContribution": last_week_total,
        "currentTier": tier,
        "currentWeekTotalContribution": current_total,
        "rewardPoolDiamonds": pool,
    }
