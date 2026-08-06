#!/usr/bin/env python3
"""MOA getFamilyPkPage PK 列表 + 收礼榜区间 → 匹配验收结果写入钉钉 Sheet4。"""

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

from family_pk_tab_to_workbook import (  # noqa: E402
    DEFAULT_WORKBOOK,
    _ensure_sheet,
    _write_sheet_replace,
)
from family_pk_page_moa import fetch_family_pk_page_data, parse_moa_pk_pairs  # noqa: E402
from mse_config_export import _fetch_mse_config  # noqa: E402
from mse_json_to_workbook import _merge_config  # noqa: E402
from mse_workbook_utils import format_rank_range, node_id  # noqa: E402
from family_pk_calc_utils import rename_family_pk_workbook, sort_match_verify_detail_rows  # noqa: E402
from alidocs_excel_export import _excel_env, _get_token_and_operator  # noqa: E402

import httpx  # noqa: E402

DEFAULT_SHEET = "匹配验收"
DATA_HEADER = [
    "MOA序",
    "家族ID",
    "家族名称",
    "对手家族ID",
    "对手名称",
    "家族收礼名次",
    "家族收礼值",
    "家族匹配区间",
    "对手收礼名次",
    "对手收礼值",
    "对手匹配区间",
    "配对无重复",
    "同区间",
    "验收",
]


def _normalize_date(text: str) -> str:
    value = text.strip()
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return value
    raise ValueError(f"日期须为 yyyy-MM-dd: {text!r}")


def _prev_day(pk_date: str) -> str:
    return (datetime.strptime(pk_date, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()


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


def bracket_for_rank(rank: int | None, brackets: list[dict[str, Any]]) -> dict[str, Any]:
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


def family_bracket_info(
    family_id: str,
    rank_map: dict[str, dict[str, Any]],
    brackets: list[dict[str, Any]],
) -> tuple[str, str, str]:
    item = rank_map.get(family_id) or {}
    rank = item.get("rank")
    score = item.get("receiveScore")
    rank_text = "" if rank is None else str(rank)
    score_text = "" if score is None else str(score)
    bracket = bracket_for_rank(int(rank) if rank is not None else None, brackets)
    label = format_rank_range(bracket.get("rankStart"), bracket.get("rankEnd"))
    return rank_text, score_text, label


def build_verify_rows(
    *,
    pk_date: str,
    rank_date: str,
    user_id: str,
    area: str = "MENA",
) -> tuple[list[list[Any]], dict[str, Any]]:
    fetched = _fetch_mse_config(namespace="voga-common", config_key="familyPkConfig")
    config = _merge_config(fetched["configValue"])
    brackets = config.get("bracketGradients") or []
    if not brackets:
        raise RuntimeError("familyPkConfig 缺少 bracketGradients")

    rank_map = load_receive_rank(rank_date)
    page_data = fetch_family_pk_page_data(user_id=user_id, pk_date=pk_date, area=area)
    pk_list = page_data.get("pkList") or []
    parsed = parse_moa_pk_pairs(pk_list)
    entries = parsed["entries"]
    if not entries:
        raise RuntimeError("MOA pkList 为空，无法验收匹配")

    response_date = str(page_data.get("date") or "").strip()
    date_aligned = not response_date or response_date == pk_date

    pair_consistent = bool(parsed["pairConsistent"])
    detail_rows: list[list[Any]] = []
    pass_count = 0
    fail_count = 0
    failures: list[str] = []

    for item in entries:
        idx = item["index"]
        fa = item["familyId"]
        fan = item["familyName"]
        fb = item["opponentId"]
        fbn = item["opponentName"]
        bye = item["bye"]

        ra, sa, la = family_bracket_info(fa, rank_map, brackets)
        dup_ok = pair_consistent
        if bye:
            rb = sb = lb = ""
            same = True
            status = "通过" if dup_ok else "失败"
        else:
            rb, sb, lb = family_bracket_info(fb, rank_map, brackets)
            same = la == lb
            status = "通过" if (same and dup_ok) else "失败"

        if status == "通过":
            pass_count += 1
        else:
            fail_count += 1
            if not same and fb:
                failures.append(f"{fa}({la}) vs {fb}({lb})")

        detail_rows.append(
            [
                idx,
                fa,
                fan,
                fb,
                fbn,
                ra,
                sa,
                la,
                rb,
                sb,
                lb,
                "是" if dup_ok else "否",
                "是" if same else "否",
                status,
            ]
        )

    if not pair_consistent:
        failures.extend(parsed["duplicateErrors"])

    detail_rows = sort_match_verify_detail_rows(detail_rows)

    summary = {
        "pkDate": pk_date,
        "rankDate": rank_date,
        "userId": user_id,
        "requestDate": page_data.get("_requestDate") or pk_date,
        "responseDate": response_date or None,
        "dateAligned": date_aligned,
        "source": "moa",
        "method": "getFamilyPkPage",
        "bracketCount": len(brackets),
        "pkListEntries": parsed["entryCount"],
        "pairCount": parsed["pairCount"],
        "byeCount": parsed["byeCount"],
        "uniqueFamilyCount": parsed["uniqueFamilyCount"],
        "pairConsistent": pair_consistent,
        "duplicateErrors": parsed["duplicateErrors"],
        "pairRows": len(detail_rows),
        "passCount": pass_count,
        "failCount": fail_count,
        "failures": failures,
        "allPass": fail_count == 0 and pair_consistent,
    }

    sheet_rows: list[list[Any]] = [
        [
            "验收摘要",
            f"PK日期={pk_date}",
            f"收礼榜={rank_date}",
            f"MOA pkList={parsed['entryCount']}条",
            f"对战={parsed['pairCount']} 轮空={parsed['byeCount']}",
            f"家族数={parsed['uniqueFamilyCount']}",
            f"通过={pass_count} 失败={fail_count}",
        ],
        [
            "MOA来源",
            f"userId={user_id}",
            f"请求date={pk_date}",
            f"响应date={response_date or '-'}",
            f"配对无重复={'是' if pair_consistent else '否'}",
            f"区间验收={'全通过' if fail_count == 0 else '有失败'}",
            "",
        ],
        [
            "规则说明",
            "MOA getFamilyPkPage pkList 对战验收",
            "每家族仅允许出现一次",
            "对战双方须同收礼榜区间",
            "末位区间可轮空",
            "",
            "",
        ],
        [],
        DATA_HEADER,
        *detail_rows,
    ]
    return sheet_rows, summary


async def write_verify_sheet_async(
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


def export_match_verify_to_workbook(
    *,
    workbook: str,
    user_id: str,
    pk_date: str,
    rank_date: str | None,
    area: str,
    sheet_name: str,
) -> dict[str, Any]:
    pk_date = _normalize_date(pk_date)
    rank_date = _normalize_date(rank_date) if rank_date else _prev_day(pk_date)
    sheet_rows, summary = build_verify_rows(
        pk_date=pk_date,
        rank_date=rank_date,
        user_id=user_id,
        area=area,
    )
    doc_url = asyncio.run(
        write_verify_sheet_async(workbook, sheet_rows, sheet_name=sheet_name)
    )
    workbook_title = rename_family_pk_workbook(workbook, pk_date)
    out_path = tmp_dir() / f"family_pk_match_verify_{pk_date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary["workbookUrl"] = doc_url
    summary["workbookTitle"] = workbook_title
    summary["sheetName"] = sheet_name
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["reportPath"] = str(out_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="家族PK匹配验收（MOA getFamilyPkPage）→ 钉钉 Sheet4")
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK, help="钉钉表格 URL/nodeId")
    parser.add_argument(
        "--user-id",
        "--momoid",
        dest="user_id",
        default="100486375",
        help="MOA 请求账号 userId（--momoid 为兼容别名）",
    )
    parser.add_argument("--pk-date", default="2026-07-02", help="PK/匹配日期 yyyy-MM-dd")
    parser.add_argument(
        "--rank-date",
        help="收礼榜日期（默认 pk-date 前一日）",
    )
    parser.add_argument("--area", default="MENA", help="请求 area（默认 MENA）")
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET, help="Sheet4 名称")
    args = parser.parse_args()

    try:
        summary = export_match_verify_to_workbook(
            workbook=args.workbook.strip(),
            user_id=str(args.user_id).strip(),
            pk_date=args.pk_date.strip(),
            rank_date=args.rank_date.strip() if args.rank_date else None,
            area=str(args.area).strip().upper() or "MENA",
            sheet_name=args.sheet_name.strip() or DEFAULT_SHEET,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("allPass") else 2


if __name__ == "__main__":
    raise SystemExit(main())
