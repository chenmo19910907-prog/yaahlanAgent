#!/usr/bin/env python3
"""汇总家族 PK 六步验收数据 → 新建钉钉 Sheet「测试结果」。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
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

from family_pk_calc_utils import family_pk_workbook_title, rename_family_pk_workbook  # noqa: E402
from family_pk_reorder_sheets import reorder_family_pk_sheets  # noqa: E402
from family_pk_tab_to_workbook import (  # noqa: E402
    DEFAULT_WORKBOOK,
    _ensure_sheet,
    _write_sheet_replace,
)
from mse_workbook_utils import fetch_workbook_sheets, node_id  # noqa: E402
from alidocs_excel_export import _excel_env, _get_token_and_operator  # noqa: E402

import httpx  # noqa: E402

DEFAULT_SHEET = "测试结果"
SUMMARY_HEADER = ["步骤", "名称", "产出Sheet", "验收项", "样本数", "通过", "失败", "结论", "备注"]
MISMATCH_HEADER = ["userId", "家族ID", "家族名称", "应发钻石", "实发钻石", "验收", "备注"]


def _normalize_date(text: str) -> str:
    value = text.strip()
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return value
    raise ValueError(f"日期须为 yyyy-MM-dd: {text!r}")


def _prev_day(pk_date: str) -> str:
    return (datetime.strptime(pk_date, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()


def _cell(row: list[Any], idx: int) -> str:
    if idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


def _parse_kv_cells(cells: list[Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for cell in cells[1:]:
        text = str(cell or "").strip()
        if not text or "=" not in text:
            continue
        key, value = text.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _find_row(rows: list[list[Any]], label: str) -> list[Any] | None:
    for row in rows:
        if _cell(row, 0) == label:
            return row
    return None


def _find_header_index(rows: list[list[Any]], header_name: str) -> tuple[int, list[str]] | None:
    for row in rows:
        headers = [_cell(row, i) for i in range(len(row))]
        if header_name in headers:
            return headers.index(header_name), headers
    return None


def _count_status(rows: list[list[Any]], header_name: str, pass_value: str = "通过") -> tuple[int, int, int]:
    found = _find_header_index(rows, header_name)
    if not found:
        return 0, 0, 0
    col_idx, headers = found
    header_row_idx = next(
        i for i, row in enumerate(rows) if [_cell(row, j) for j in range(len(row))] == headers
    )
    total = 0
    passed = 0
    failed = 0
    for row in rows[header_row_idx + 1 :]:
        if not any(_cell(row, j) for j in range(len(row))):
            continue
        if _cell(row, 0) in ("验收摘要", "测算摘要", "规则说明", "MOA来源"):
            break
        status = _cell(row, col_idx)
        if not status:
            continue
        total += 1
        if status == pass_value:
            passed += 1
        else:
            failed += 1
    return total, passed, failed


def _parse_param_sheet(rows: list[list[Any]]) -> dict[str, Any]:
    keys = {"minWinPk", "minRewardPk", "minListPk", "basePoolDiamond"}
    found: dict[str, str] = {}
    for row in rows:
        if _cell(row, 0) == "基础" and _cell(row, 1) in keys:
            found[_cell(row, 1)] = _cell(row, 2)
    ok = bool(found.get("minWinPk")) and bool(found.get("minRewardPk"))
    note = (
        f"minWinPk={found.get('minWinPk', '-')}, minListPk={found.get('minListPk', '-')}"
        if ok
        else "参数表缺少关键字段"
    )
    return {
        "ok": ok,
        "total": len(found),
        "pass": len(found) if ok else 0,
        "fail": 0 if ok else 1,
        "note": note,
    }


def _parse_family_list(rows: list[list[Any]]) -> dict[str, Any]:
    header = _find_header_index(rows, "家族ID")
    if not header:
        return {"ok": False, "total": 0, "pass": 0, "fail": 1, "families": 0, "members": 0, "note": "未找到家族列表表头"}
    _, headers = header
    idx_fid = headers.index("家族ID")
    header_row_idx = next(
        i for i, row in enumerate(rows) if [_cell(row, j) for j in range(len(row))] == headers
    )
    families: set[str] = set()
    members = 0
    for row in rows[header_row_idx + 1 :]:
        fid = _cell(row, idx_fid)
        if not fid.isdigit():
            continue
        families.add(fid)
        members += 1
    ok = members > 0
    return {
        "ok": ok,
        "total": members,
        "pass": members if ok else 0,
        "fail": 0 if ok else 1,
        "families": len(families),
        "members": members,
        "note": f"{len(families)} 家族 / {members} 成员",
    }


def _parse_tier_sheet(rows: list[list[Any]]) -> dict[str, Any]:
    summary = _find_row(rows, "测算摘要")
    kv = _parse_kv_cells(summary or [])
    families = int(kv.get("家族数") or 0)
    tier_rows = int(kv.get("明细行") or 0)
    ok = families > 0 and tier_rows > 0
    return {
        "ok": ok,
        "total": tier_rows,
        "pass": tier_rows if ok else 0,
        "fail": 0 if ok else 1,
        "note": f"收礼榜日期={kv.get('收礼榜日期', '-')}",
    }


def _parse_match_sheet(rows: list[list[Any]]) -> dict[str, Any]:
    summary = _find_row(rows, "验收摘要")
    kv = _parse_kv_cells(summary or [])
    pass_text = kv.get("通过", "")
    fail_text = kv.get("失败", "")
    m_pass = re.search(r"\d+", pass_text)
    m_fail = re.search(r"\d+", fail_text)
    passed = int(m_pass.group()) if m_pass else 0
    failed = int(m_fail.group()) if m_fail else 0
    total, cnt_pass, cnt_fail = _count_status(rows, "验收")
    if total:
        passed, failed = cnt_pass, cnt_fail
    ok = failed == 0 and passed > 0
    return {
        "ok": ok,
        "total": passed + failed,
        "pass": passed,
        "fail": failed,
        "note": f"对战={kv.get('对战', '-')}",
    }


def _parse_reward_sheet(rows: list[list[Any]]) -> dict[str, Any]:
    summary = _find_row(rows, "测算摘要")
    kv = _parse_kv_cells(summary or [])
    member_rows = int(kv.get("成员行数") or 0)
    expected_total = kv.get("应发钻合计", "")
    contrib_match = re.search(r"榜单验收 通过=(\d+) 失败=(\d+)", " ".join(_cell(summary or [], i) for i in range(10)))
    contrib_pass = contrib_fail = None
    if contrib_match:
        contrib_pass = int(contrib_match.group(1))
        contrib_fail = int(contrib_match.group(2))
    return {
        "member_rows": member_rows,
        "expected_total": expected_total,
        "contrib_pass": contrib_pass,
        "contrib_fail": contrib_fail,
    }


def _parse_dispatch_sheet(rows: list[list[Any]]) -> dict[str, Any]:
    summary = _find_row(rows, "验收摘要")
    kv = _parse_kv_cells(summary or [])
    passed = int(re.search(r"\d+", kv.get("通过", "0")).group()) if re.search(r"\d+", kv.get("通过", "0")) else 0
    failed = int(re.search(r"\d+", kv.get("不一致", "0")).group()) if re.search(r"\d+", kv.get("不一致", "0")) else 0
    total, cnt_pass, cnt_fail = _count_status(rows, "验收")
    if total:
        passed, failed = cnt_pass, cnt_fail
    mismatches: list[dict[str, str]] = []
    header = _find_header_index(rows, "验收")
    if header:
        status_idx, headers = header
        uid_idx = headers.index("成员userId") if "成员userId" in headers else -1
        fid_idx = headers.index("家族ID") if "家族ID" in headers else -1
        fname_idx = headers.index("家族名称") if "家族名称" in headers else -1
        expected_idx = headers.index("应发钻石") if "应发钻石" in headers else -1
        delta_idx = headers.index("实发钻石") if "实发钻石" in headers else -1
        header_row_idx = next(
            i for i, row in enumerate(rows) if [_cell(row, j) for j in range(len(row))] == headers
        )
        for row in rows[header_row_idx + 1 :]:
            status = _cell(row, status_idx)
            if status != "通过" and _cell(row, uid_idx):
                mismatches.append(
                    {
                        "userId": _cell(row, uid_idx),
                        "familyId": _cell(row, fid_idx),
                        "familyName": _cell(row, fname_idx),
                        "expected": _cell(row, expected_idx),
                        "delta": _cell(row, delta_idx),
                        "status": status,
                    }
                )
    ok = failed == 0 and passed > 0
    return {
        "ok": ok,
        "total": passed + failed,
        "pass": passed,
        "fail": failed,
        "expected_total": kv.get("应发钻", ""),
        "actual_total": kv.get("实发钻合计", ""),
        "settle_date": kv.get("发奖任务入参", ""),
        "mismatches": mismatches,
    }


def _conclusion(ok: bool, *, partial: bool = False) -> str:
    if ok:
        return "通过"
    if partial:
        return "部分通过"
    return "失败"


def build_test_result_rows(
    *,
    pk_date: str,
    rank_date: str,
    user_id: str,
    sheets: dict[str, list[list[Any]]],
    executed_at: str,
) -> tuple[list[list[Any]], dict[str, Any]]:
    param = _parse_param_sheet(sheets.get("参数表", []))
    families = _parse_family_list(sheets.get("家族列表", []))
    tier = _parse_tier_sheet(sheets.get("家族PK档位", []))
    match = _parse_match_sheet(sheets.get("匹配验收", []))
    reward = _parse_reward_sheet(sheets.get("用户发钻测试", []))
    dispatch = _parse_dispatch_sheet(sheets.get("发钻实发验收", []))

    contrib_pass = reward.get("contrib_pass")
    contrib_fail = reward.get("contrib_fail")
    contrib_total = (contrib_pass or 0) + (contrib_fail or 0)
    contrib_ok = contrib_fail == 0 and (contrib_pass or 0) > 0

    step_rows: list[list[Any]] = [
        [
            0,
            "新建测试表",
            "（整表）",
            "Sheet 预建",
            6,
            6,
            0,
            "通过",
            "参数表/家族列表/家族PK档位/匹配验收/用户发钻测试/发钻实发验收",
        ],
        [
            1,
            "MSE同步参数表",
            "参数表",
            "familyPkConfig",
            param["total"],
            param["pass"],
            param["fail"],
            _conclusion(param["ok"]),
            param["note"],
        ],
        [
            2,
            "家族列表",
            "家族列表",
            "MENA族长家族+成员",
            families["members"],
            families["pass"],
            families["fail"],
            _conclusion(families["ok"]),
            families["note"],
        ],
        [
            3,
            "收礼榜与档位",
            "家族PK档位",
            "档位达标PK测算",
            tier["total"],
            tier["pass"],
            tier["fail"],
            _conclusion(tier["ok"]),
            tier["note"],
        ],
        [
            4,
            "匹配验收",
            "匹配验收",
            "同区间对战匹配",
            match["total"],
            match["pass"],
            match["fail"],
            _conclusion(match["ok"]),
            match["note"],
        ],
        [
            5,
            "成员PK造数测算",
            "用户发钻测试",
            "应发钻石测算",
            reward["member_rows"],
            reward["member_rows"],
            0,
            _conclusion(reward["member_rows"] > 0),
            f"应发钻合计={reward['expected_total']}",
        ],
        [
            "6a",
            "发奖实发验收",
            "发钻实发验收",
            "应发vs实发查钻",
            dispatch["total"],
            dispatch["pass"],
            dispatch["fail"],
            _conclusion(dispatch["ok"], partial=dispatch["fail"] > 0 and dispatch["pass"] > 0),
            f"应发={dispatch['expected_total']} 实发={dispatch['actual_total']}",
        ],
        [
            "6b",
            "贡献榜验收",
            "用户发钻测试",
            "榜单PK/钻/验收",
            contrib_total,
            contrib_pass if contrib_pass is not None else "",
            contrib_fail if contrib_fail is not None else "",
            _conclusion(contrib_ok) if contrib_pass is not None else "未执行",
            "用户PK<minListPk 不在榜记通过",
        ],
    ]

    core_ok = all(
        [
            param["ok"],
            families["ok"],
            tier["ok"],
            match["ok"],
            reward["member_rows"] > 0,
            contrib_ok if contrib_pass is not None else True,
        ]
    )
    dispatch_ok = dispatch["ok"]
    overall = "通过" if core_ok and dispatch_ok else ("部分通过" if core_ok else "失败")

    rows: list[list[Any]] = [
        [
            "测试摘要",
            f"PK日期={pk_date}",
            f"收礼榜={rank_date}",
            f"MOA账号={user_id}",
            f"执行时间={executed_at}",
            f"总体验收={overall}",
            "",
            "",
        ],
        [],
        SUMMARY_HEADER,
        *step_rows,
        [],
        ["总体验收结论", overall, "", "", "", "", "", "", ""],
    ]

    mismatches = dispatch.get("mismatches") or []
    if mismatches:
        rows.extend(
            [
                [],
                ["发钻不一致明细"],
                MISMATCH_HEADER,
            ]
        )
        for item in mismatches:
            note = ""
            expected = int(item.get("expected") or 0)
            delta = int(item.get("delta") or 0)
            if expected > 0 and delta == expected * 2:
                note = "疑似重复发奖"
            elif expected > 0 and delta == 0:
                note = "未到账"
            elif delta < 0:
                note = "实发少于应发"
            rows.append(
                [
                    item.get("userId", ""),
                    item.get("familyId", ""),
                    item.get("familyName", ""),
                    item.get("expected", ""),
                    item.get("delta", ""),
                    item.get("status", ""),
                    note,
                ]
            )

    summary = {
        "pkDate": pk_date,
        "rankDate": rank_date,
        "userId": user_id,
        "executedAt": executed_at,
        "overall": overall,
        "param": param,
        "families": families,
        "tier": tier,
        "match": match,
        "reward": reward,
        "dispatch": dispatch,
        "contribPass": contrib_pass,
        "contribFail": contrib_fail,
        "mismatchCount": len(mismatches),
    }
    return rows, summary


async def write_test_result_sheet_async(
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


def export_test_result_to_workbook(
    *,
    workbook: str,
    pk_date: str,
    rank_date: str | None = None,
    user_id: str = "100486375",
    sheet_name: str = DEFAULT_SHEET,
) -> dict[str, Any]:
    pk_date = _normalize_date(pk_date)
    rank_date = _normalize_date(rank_date) if rank_date else _prev_day(pk_date)
    sheets = fetch_workbook_sheets(workbook)
    executed_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    rows, summary = build_test_result_rows(
        pk_date=pk_date,
        rank_date=rank_date,
        user_id=user_id,
        sheets=sheets,
        executed_at=executed_at,
    )
    doc_url = asyncio.run(
        write_test_result_sheet_async(workbook, rows, sheet_name=sheet_name)
    )
    workbook_title = family_pk_workbook_title(pk_date)
    out_path = REPO_ROOT / ".tmp" / f"family_pk_test_result_{pk_date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary.update(
        {
            "workbookUrl": doc_url,
            "workbookTitle": workbook_title,
            "sheetName": sheet_name,
            "reportPath": str(out_path),
        }
    )
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    sheet_order = reorder_family_pk_sheets(doc_url)
    summary["sheetOrder"] = sheet_order
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="家族 PK 六步验收汇总 → 钉钉「测试结果」")
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK)
    parser.add_argument("--pk-date", required=True)
    parser.add_argument("--rank-date", default="")
    parser.add_argument("--user-id", "--momoid", dest="user_id", default="100486375")
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET)
    args = parser.parse_args()
    try:
        summary = export_test_result_to_workbook(
            workbook=args.workbook.strip(),
            pk_date=args.pk_date.strip(),
            rank_date=args.rank_date.strip() or None,
            user_id=str(args.user_id).strip(),
            sheet_name=args.sheet_name.strip() or DEFAULT_SHEET,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("overall") == "通过" else 2


if __name__ == "__main__":
    raise SystemExit(main())
