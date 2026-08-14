#!/usr/bin/env python3
"""家族基金：快照 + 成员贡献/应发钻/实发验收 → 单表「家族基金测试」。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parents[1]
_EXCEL_VENV = (
    REPO_ROOT / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel/venv/bin/python3.13"
)

if (
    __name__ == "__main__"
    and _EXCEL_VENV.is_file()
    and Path(sys.executable).resolve() != _EXCEL_VENV.resolve()
):
    os.execv(str(_EXCEL_VENV), [str(_EXCEL_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from repo_paths import admin_execute_path  # noqa: E402

from alidocs_excel_export import _excel_env, _get_token_and_operator  # noqa: E402
from family_fund_calc_utils import (  # noqa: E402
    FAMILY_FUND_TEST_HEADER,
    FAMILY_FUND_TEST_SHEET,
    LEGACY_SHEETS,
    compute_member_expected_diamonds,
    load_family_fund_config_from_workbook,
    rename_family_fund_workbook_async,
)
from family_fund_moa_query import (  # noqa: E402
    build_family_fund_snapshot,
    build_member_rank_list,
    normalize_week_monday,
)
from user_phone_lookup import batch_user_phones  # noqa: E402
from family_pk_tab_to_workbook import _delete_sheet, _ensure_sheet, _write_sheet_replace  # noqa: E402
from mse_workbook_utils import node_id  # noqa: E402

import httpx  # noqa: E402


def _query_admin_family_name(family_id: str) -> str:
    proc = subprocess.run(
        [
            sys.executable,
            str(admin_execute_path()),
            "--query-family",
            "--family-id",
            family_id,
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return ""
    body = json.loads(proc.stdout)
    items = body.get("items") or []
    if items:
        return str(items[0].get("familyName") or "")
    return ""


def build_family_fund_test_rows(
    *,
    week_monday: str,
    family_id: str,
    family_name: str,
    snapshot: dict[str, Any],
    expected: list[dict[str, Any]],
    phone_map: dict[str, str],
    min_rank: int,
) -> list[list[Any]]:
    pool = int(snapshot["rewardPoolDiamonds"])
    rows: list[list[Any]] = [FAMILY_FUND_TEST_HEADER]
    for row in expected:
        uid = str(row["userId"])
        rows.append(
            [
                week_monday,
                family_id,
                family_name,
                snapshot["lastWeekTotalContribution"],
                snapshot["currentTier"],
                snapshot["currentWeekTotalContribution"],
                pool,
                uid,
                phone_map.get(uid, ""),
                row["rank"] if row["rank"] is not None else "30+",
                row["contribution"],
                "Y" if row["eligible"] else "N",
                f"{row['shareRatio']:.6f}" if row["shareRatio"] else "0",
                row["expectedDiamond"],
                "",
                "",
                "",
            ]
        )
    return rows


async def _cleanup_legacy_sheets(
    *,
    token: str,
    operator: str,
    workbook_id: str,
) -> None:
    async with httpx.AsyncClient(timeout=120) as client:
        for name in LEGACY_SHEETS:
            try:
                await _delete_sheet(
                    token=token,
                    operator=operator,
                    workbook_id=workbook_id,
                    sheet_name=name,
                    client=client,
                )
            except RuntimeError:
                pass


async def write_family_fund_data_async(
    workbook: str,
    *,
    family_id: str,
    week_monday: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    week_monday = normalize_week_monday(week_monday)
    family_name = _query_admin_family_name(family_id)
    snapshot = build_family_fund_snapshot(
        family_id=family_id,
        week_monday=week_monday,
        config=config,
        admin_family_name=family_name,
    )
    min_rank = int(config.get("minContributionToRank") or 500)
    members = build_member_rank_list(
        family_id=family_id,
        week_key=snapshot["weekKey"],
        min_contribution_to_rank=min_rank,
    )
    expected = compute_member_expected_diamonds(
        config=config,
        pool=int(snapshot["rewardPoolDiamonds"]),
        members=members,
    )
    phone_map = batch_user_phones(m["userId"] for m in members)
    test_rows = build_family_fund_test_rows(
        week_monday=week_monday,
        family_id=family_id,
        family_name=family_name,
        snapshot=snapshot,
        expected=expected,
        phone_map=phone_map,
        min_rank=min_rank,
    )

    workbook_id = node_id(workbook)
    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    async with httpx.AsyncClient(timeout=120) as client:
        await _ensure_sheet(
            token=token,
            operator=operator,
            workbook_id=workbook_id,
            sheet_name=FAMILY_FUND_TEST_SHEET,
            client=client,
        )
    await _cleanup_legacy_sheets(token=token, operator=operator, workbook_id=workbook_id)
    str_rows = [[str(c) for c in r] for r in test_rows]
    await _write_sheet_replace(
        token=token,
        operator=operator,
        workbook_id=workbook_id,
        sheet_name=FAMILY_FUND_TEST_SHEET,
        rows=str_rows,
    )
    await rename_family_fund_workbook_async(workbook, week_monday)
    return {
        "workbookUrl": f"https://alidocs.dingtalk.com/i/nodes/{workbook_id}",
        "sheetName": FAMILY_FUND_TEST_SHEET,
        "familyId": family_id,
        "weekMonday": week_monday,
        "snapshot": snapshot,
        "memberCount": len(members),
        "eligibleCount": sum(1 for m in members if m["contribution"] >= min_rank),
        "expectedTotalDiamonds": sum(int(r["expectedDiamond"]) for r in expected),
    }


def write_family_fund_data(workbook: str, **kwargs: Any) -> dict[str, Any]:
    config = load_family_fund_config_from_workbook(workbook)
    return asyncio.run(write_family_fund_data_async(workbook, config=config, **kwargs))


def main() -> int:
    parser = argparse.ArgumentParser(description="家族基金数据写入钉钉单表")
    parser.add_argument("workbook", help="钉钉表格 URL 或 nodeId")
    parser.add_argument("--family-id", required=True)
    parser.add_argument("--week-monday", required=True, help="周期周一 yyyy-MM-dd")
    args = parser.parse_args()
    try:
        summary = write_family_fund_data(
            args.workbook.strip(),
            family_id=args.family_id.strip(),
            week_monday=args.week_monday.strip(),
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
