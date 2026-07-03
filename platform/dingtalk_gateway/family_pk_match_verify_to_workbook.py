#!/usr/bin/env python3
"""抓包 PK 列表 + 收礼榜区间 → 匹配验收结果写入钉钉 Sheet3。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
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

from family_pk_tab_to_workbook import (  # noqa: E402
    DEFAULT_WORKBOOK,
    _ensure_sheet,
    _write_sheet_replace,
)
from family_pk_tunnel_capture import find_pk_page_capture, print_capture_user_prompt  # noqa: E402
from mse_config_export import _fetch_mse_config  # noqa: E402
from mse_json_to_workbook import _merge_config  # noqa: E402
from mse_workbook_utils import format_rank_range, node_id  # noqa: E402
from family_pk_calc_utils import rename_family_pk_workbook, sort_match_verify_detail_rows  # noqa: E402
from alidocs_excel_export import _excel_env, _get_token_and_operator  # noqa: E402

import httpx  # noqa: E402

DEFAULT_SHEET = "匹配验收"
DATA_HEADER = [
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
    "同区间",
    "验收",
    "说明",
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
            str(REPO_ROOT / "MOA/moa_execute.py"),
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
    momoid: str,
    since: int,
    wait_seconds: int = 180,
    poll_interval_ms: int = 3000,
    fresh_capture: bool = False,
) -> tuple[list[list[Any]], dict[str, Any]]:
    fetched = _fetch_mse_config(namespace="voga-common", config_key="familyPkConfig")
    config = _merge_config(fetched["configValue"])
    brackets = config.get("bracketGradients") or []
    if not brackets:
        raise RuntimeError("familyPkConfig 缺少 bracketGradients")

    rank_map = load_receive_rank(rank_date)
    min_capture_epoch = time.time() if fresh_capture else None
    if wait_seconds > 0 or fresh_capture:
        print_capture_user_prompt(
            momoid=momoid,
            pk_date=pk_date,
            wait_seconds=wait_seconds,
            reason="prepare" if not fresh_capture else "not_found",
        )
    capture = find_pk_page_capture(
        momoid=momoid,
        pk_date=pk_date,
        since=since,
        wait_seconds=wait_seconds,
        poll_interval_ms=poll_interval_ms,
        announce_wait=False,
        min_capture_epoch=min_capture_epoch,
    )
    data = (capture.get("response") or {}).get("data") or {}
    pk_list = data.get("pkList") or []

    detail_rows: list[list[Any]] = []
    pass_count = 0
    fail_count = 0
    failures: list[str] = []

    for pair in pk_list:
        if not isinstance(pair, dict):
            continue
        fa_info = pair.get("familyInfo") or {}
        opp = pair.get("opponentFamily")
        fa = str(fa_info.get("familyId") or "").strip()
        fan = str(fa_info.get("name") or fa_info.get("familyName") or "").strip()
        fb = ""
        fbn = ""
        if isinstance(opp, dict) and opp.get("familyId"):
            fb = str(opp.get("familyId")).strip()
            fbn = str(opp.get("name") or opp.get("familyName") or "").strip()

        ra, sa, la = family_bracket_info(fa, rank_map, brackets)
        if fb:
            rb, sb, lb = family_bracket_info(fb, rank_map, brackets)
            same = la == lb
            note = "同区间匹配" if same else f"跨区间：{la} vs {lb}"
            status = "通过" if same else "失败"
            if same:
                pass_count += 1
            else:
                fail_count += 1
                failures.append(f"{fa}({la}) vs {fb}({lb})")
        else:
            rb = sb = lb = ""
            same = True
            note = "轮空"
            status = "通过"
            pass_count += 1

        detail_rows.append(
            [
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
                "是" if same else "否",
                status,
                note,
            ]
        )

    detail_rows = sort_match_verify_detail_rows(detail_rows)

    summary = {
        "pkDate": pk_date,
        "rankDate": rank_date,
        "momoid": momoid,
        "captureId": capture.get("_id"),
        "captureTime": capture.get("time"),
        "bracketCount": len(brackets),
        "pairRows": len(detail_rows),
        "passCount": pass_count,
        "failCount": fail_count,
        "failures": failures,
        "allPass": fail_count == 0,
    }

    sheet_rows: list[list[Any]] = [
        [
            "验收摘要",
            f"PK日期={pk_date}",
            f"收礼榜日期={rank_date}",
            f"通过={pass_count}",
            f"失败={fail_count}",
            f"抓包={capture.get('time')}",
            str(capture.get("_id") or ""),
        ],
        [
            "规则说明",
            "按参数表 bracketGradients 区间",
            "收礼榜有效名次定区间",
            "对战双方须同区间",
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
    momoid: str,
    pk_date: str,
    rank_date: str | None,
    since: int,
    wait_seconds: int,
    poll_interval_ms: int,
    sheet_name: str,
    fresh_capture: bool = False,
) -> dict[str, Any]:
    pk_date = _normalize_date(pk_date)
    rank_date = _normalize_date(rank_date) if rank_date else _prev_day(pk_date)
    sheet_rows, summary = build_verify_rows(
        pk_date=pk_date,
        rank_date=rank_date,
        momoid=momoid,
        since=since,
        wait_seconds=wait_seconds,
        poll_interval_ms=poll_interval_ms,
        fresh_capture=fresh_capture,
    )
    doc_url = asyncio.run(
        write_verify_sheet_async(workbook, sheet_rows, sheet_name=sheet_name)
    )
    workbook_title = rename_family_pk_workbook(workbook, pk_date)
    out_path = REPO_ROOT / ".tmp" / f"family_pk_match_verify_{pk_date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary["workbookUrl"] = doc_url
    summary["workbookTitle"] = workbook_title
    summary["sheetName"] = sheet_name
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["reportPath"] = str(out_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="家族PK匹配验收 → 钉钉 Sheet3")
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK, help="钉钉表格 URL/nodeId")
    parser.add_argument("--momoid", default="100465989", help="抓包账号")
    parser.add_argument("--pk-date", default="2026-07-02", help="PK/匹配日期 yyyy-MM-dd")
    parser.add_argument(
        "--rank-date",
        help="收礼榜日期（默认 pk-date 前一日）",
    )
    parser.add_argument("--since", type=int, default=259200, help="Tunnel 回溯秒数")
    parser.add_argument(
        "--wait",
        type=int,
        default=180,
        dest="wait_seconds",
        help="未命中时最长等待秒数（0=立即失败；默认等待用户在 App 刷新 PK 页）",
    )
    parser.add_argument(
        "--poll-ms",
        type=int,
        default=3000,
        dest="poll_interval_ms",
        help="抓包等待轮询间隔毫秒",
    )
    parser.add_argument(
        "--fresh-capture",
        action="store_true",
        help="忽略脚本启动前的抓包，等待重匹配后 App 刷新产生的新 getFamilyPkPage",
    )
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET, help="Sheet3 名称")
    args = parser.parse_args()

    try:
        summary = export_match_verify_to_workbook(
            workbook=args.workbook.strip(),
            momoid=str(args.momoid).strip(),
            pk_date=args.pk_date.strip(),
            rank_date=args.rank_date.strip() if args.rank_date else None,
            since=args.since,
            wait_seconds=args.wait_seconds,
            poll_interval_ms=args.poll_interval_ms,
            sheet_name=args.sheet_name.strip() or DEFAULT_SHEET,
            fresh_capture=args.fresh_capture,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("allPass") else 2


if __name__ == "__main__":
    raise SystemExit(main())
