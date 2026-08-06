#!/usr/bin/env python3
"""收礼榜 + 参数表 → 各家族档位达标 PK 与钻石奖励 → 钉钉 Sheet4。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
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

from repo_paths import (
    admin_execute_path,
    admin_module_dir,
    batch_progress_script,
    get_repo_root,
    gift_execute_path,
    gift_module_dir,
    moa_execute_path,
    moa_module_dir,
    moa_template,
    mse_execute_path,
    mse_module_dir,
    stage_gateway_url,
    tmp_dir,
)

from family_pk_calc_utils import (  # noqa: E402
    bracket_for_rank,
    calc_family_tier_rows,
    compute_bracket_daily_avgs,
    min_daily_avg_from_config,
    rename_family_pk_workbook,
)
from family_pk_tab_to_workbook import (  # noqa: E402
    DEFAULT_WORKBOOK,
    _ensure_sheet,
    _write_sheet_replace,
)
from mse_config_export import _fetch_mse_config  # noqa: E402
from mse_json_to_workbook import _merge_config  # noqa: E402
from mse_workbook_utils import fetch_workbook_sheets, format_rank_range, node_id  # noqa: E402
from alidocs_excel_export import _excel_env, _get_token_and_operator  # noqa: E402

import httpx  # noqa: E402

DEFAULT_SHEET = "家族PK档位"
MEMBER_SHEET = "家族列表"
TIER_NOTE = "有效日均=max(区间日均,minDailyAvg)；达标PK=有效日均×系数；档位钻石=达标PK×返利比例"

DATA_HEADER = [
    "PK日期",
    "收礼榜日期",
    "家族ID",
    "家族名称",
    "收礼名次",
    "收礼值",
    "成员数",
    "名次区间",
    "区间日均",
    "有效日均",
    "档位",
    "系数",
    "达标PK",
    "返利比例",
    "档位钻石",
]


def _normalize_date(text: str) -> str:
    value = text.strip()
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return value
    raise ValueError(f"日期须为 yyyy-MM-dd: {text!r}")


def _prev_day(pk_date: str) -> str:
    return (datetime.strptime(pk_date, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()


def _next_day(rank_date: str) -> str:
    return (datetime.strptime(rank_date, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()


def _resolve_dates(pk_date: str | None, rank_date: str | None) -> tuple[str, str]:
    pk = pk_date.strip() if pk_date and str(pk_date).strip() else None
    rank = rank_date.strip() if rank_date and str(rank_date).strip() else None
    if not pk and not rank:
        raise ValueError("须提供 pk-date 或 rank-date")
    if not pk:
        assert rank is not None
        pk = _next_day(rank)
    if not rank:
        rank = _prev_day(pk)
    return _normalize_date(pk), _normalize_date(rank)


def _cell(row: list[Any], idx: int) -> str:
    if idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


def load_receive_rank(rank_date: str) -> dict[str, dict[str, Any]]:
    proc = subprocess.run(
        [
            sys.executable,
            str(moa_execute_path()),
            "--family-pk-query-receive-rank",
            "--family-pk-date",
            rank_date,
            "--family-pk-limit",
            "500",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "查询收礼榜失败")[-500:])
    body = json.loads(proc.stdout[proc.stdout.find("{") :])
    return {str(x["familyId"]): x for x in body.get("rankList", [])}


def load_member_counts_from_workbook(
    workbook: str,
    *,
    sheet_name: str = MEMBER_SHEET,
) -> tuple[dict[str, int], dict[str, str]]:
    sheets = fetch_workbook_sheets(workbook)
    if sheet_name not in sheets:
        raise RuntimeError(f"未找到工作表: {sheet_name}")
    counts: dict[str, int] = {}
    names: dict[str, str] = {}
    for row in sheets[sheet_name]:
        fid = _cell(row, 0)
        fname = _cell(row, 1)
        uid = _cell(row, 2)
        if fid.isdigit():
            if fname:
                names.setdefault(fid, fname)
            if uid.isdigit():
                counts[fid] = counts.get(fid, 0) + 1
    return counts, names


def build_reward_calc_rows(
    *,
    pk_date: str,
    rank_date: str,
    workbook: str,
    member_sheet: str,
) -> tuple[list[list[Any]], dict[str, Any]]:
    fetched = _fetch_mse_config(namespace="voga-common", config_key="familyPkConfig")
    config = _merge_config(fetched["configValue"])
    brackets = config.get("bracketGradients") or []
    if not brackets:
        raise RuntimeError("familyPkConfig 缺少 bracketGradients")

    base_pool = int(config.get("basePoolDiamond", 999))
    min_daily_avg = min_daily_avg_from_config(config)
    rank_map = load_receive_rank(rank_date)
    member_counts, family_names = load_member_counts_from_workbook(
        workbook,
        sheet_name=member_sheet,
    )
    bracket_daily_avgs = compute_bracket_daily_avgs(rank_map, brackets)

    detail_rows: list[list[Any]] = []
    families_with_rank = 0
    tier_rows = 0

    for family_id, item in sorted(
        rank_map.items(),
        key=lambda kv: int(kv[1].get("rank") or 999999),
    ):
        rank = item.get("rank")
        if rank is None:
            continue
        families_with_rank += 1
        receive_score = int(item.get("receiveScore") or 0)
        member_count = member_counts.get(family_id, 0)
        family_name = family_names.get(family_id, "")
        bracket = bracket_for_rank(int(rank), brackets)
        bracket_label = format_rank_range(bracket.get("rankStart"), bracket.get("rankEnd"))
        family_rows = calc_family_tier_rows(
            pk_date=pk_date,
            rank_date=rank_date,
            family_id=family_id,
            family_name=family_name,
            rank=int(rank),
            receive_score=receive_score,
            member_count=member_count,
            bracket_label=bracket_label,
            bracket=bracket,
            bracket_daily_avg=bracket_daily_avgs.get(bracket_label, 0.0),
            min_bracket_daily_avg=min_daily_avg,
        )
        tier_rows += len(family_rows)
        detail_rows.extend(family_rows)

    summary = {
        "pkDate": pk_date,
        "rankDate": rank_date,
        "basePoolDiamond": base_pool,
        "minDailyAvg": min_daily_avg,
        "bracketCount": len(brackets),
        "rankFamilies": families_with_rank,
        "tierRows": tier_rows,
        "memberSheet": member_sheet,
        "bracketDailyAvgs": {k: round(v, 2) for k, v in bracket_daily_avgs.items()},
    }

    sheet_rows: list[list[Any]] = [
        [
            "测算摘要",
            f"PK日期={pk_date}",
            f"收礼榜日期={rank_date}",
            f"家族数={families_with_rank}",
            f"明细行={tier_rows}",
            f"basePool={base_pool}",
            f"minDailyAvg={min_daily_avg}",
        ],
        [
            "规则说明",
            TIER_NOTE,
            "区间日均=同区间家族收礼值均值",
            "同区间家族共用区间日均与达标PK",
            "参数来自 MSE familyPkConfig",
            "",
            "",
        ],
        [],
        DATA_HEADER,
        *detail_rows,
    ]
    return sheet_rows, summary


async def write_reward_calc_sheet_async(
    workbook_url_or_id: str,
    rows: list[list[Any]],
    *,
    sheet_name: str = DEFAULT_SHEET,
) -> str:
    workbook_id = node_id(workbook_url_or_id)
    url = f"https://alidocs.dingtalk.com/i/nodes/{workbook_id}"
    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    str_rows = [[str(c) if c is not None else "" for c in row] for row in rows]
    async with httpx.AsyncClient(timeout=120) as client:
        await _ensure_sheet(
            token=token,
            operator=operator,
            workbook_id=workbook_id,
            sheet_name=sheet_name,
            client=client,
        )
    await _write_sheet_replace(
        token=token,
        operator=operator,
        workbook_id=workbook_id,
        sheet_name=sheet_name,
        rows=str_rows,
    )
    return url


def export_reward_calc_to_workbook(
    *,
    workbook: str,
    pk_date: str | None,
    rank_date: str | None,
    sheet_name: str,
    member_sheet: str,
) -> dict[str, Any]:
    pk_date, rank_date = _resolve_dates(pk_date, rank_date)
    sheet_rows, summary = build_reward_calc_rows(
        pk_date=pk_date,
        rank_date=rank_date,
        workbook=workbook,
        member_sheet=member_sheet,
    )
    doc_url = asyncio.run(
        write_reward_calc_sheet_async(workbook, sheet_rows, sheet_name=sheet_name)
    )
    workbook_title = rename_family_pk_workbook(workbook, pk_date)
    out_path = tmp_dir() / f"family_pk_reward_calc_{pk_date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary["workbookUrl"] = doc_url
    summary["workbookTitle"] = workbook_title
    summary["sheetName"] = sheet_name
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["reportPath"] = str(out_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="家族PK档位达标与奖励测算 → 钉钉 Sheet4")
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK, help="钉钉表格 URL/nodeId")
    parser.add_argument("--pk-date", help="PK/匹配日期 yyyy-MM-dd（默认 rank-date 次日）")
    parser.add_argument("--rank-date", help="收礼榜日期（默认 pk-date 前一日）")
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET, help="Sheet3 名称")
    parser.add_argument("--member-sheet", default=MEMBER_SHEET, help="成员数来源 Sheet")
    args = parser.parse_args()

    try:
        summary = export_reward_calc_to_workbook(
            workbook=args.workbook.strip(),
            pk_date=args.pk_date.strip() if args.pk_date else None,
            rank_date=args.rank_date.strip() if args.rank_date else None,
            sheet_name=args.sheet_name.strip() or DEFAULT_SHEET,
            member_sheet=args.member_sheet.strip() or MEMBER_SHEET,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
