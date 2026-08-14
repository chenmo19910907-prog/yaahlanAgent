#!/usr/bin/env python3
"""家族基金：清除下发锁 → 结算发奖（可选）→ 查钻验收 → 回写「家族基金测试」单表。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
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

from repo_paths import moa_execute_path, moa_template  # noqa: E402

from alidocs_excel_export import _excel_env, _get_token_and_operator  # noqa: E402
from family_fund_calc_utils import (  # noqa: E402
    CALC_SHEET,
    FAMILY_FUND_TEST_HEADER,
    compute_member_expected_diamonds,
    rename_family_fund_workbook_async,
)
from family_fund_moa_query import (  # noqa: E402
    assign_contribution_ranks,
    normalize_week_monday,
    week_monday_for_dispatch_offset,
)
from family_pk_tab_to_workbook import _write_sheet_replace  # noqa: E402
from mse_workbook_utils import fetch_workbook_sheets_async, node_id  # noqa: E402

_DIAMOND_TPL = moa_template("钻石-查询余额.json")
_DISPATCH_TPL = moa_template("家族基金-奖励下发.json")
_CLEAR_DISPATCH_TPL = moa_template("家族基金-清除奖励下发记录.json")


def _cell(row: list[Any], idx: int) -> str:
    if idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


def query_diamond(user_id: str) -> int:
    proc = subprocess.run(
        [
            sys.executable,
            str(moa_execute_path()),
            "--payload-file",
            str(_DIAMOND_TPL),
            "--diamond-query-user-id",
            user_id,
            "--diamond-output",
            "summary",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "查钻失败")[-400:])
    text = proc.stdout
    summary = json.loads(text[text.find("{") : text.rfind("}") + 1])
    return int(summary["diamonds"])


def run_family_fund_reward_dispatch_clear(
    *,
    week_monday: str,
    dispatch_offset: int = 0,
) -> None:
    target_monday = week_monday_for_dispatch_offset(week_monday, dispatch_offset)
    proc = subprocess.run(
        [
            sys.executable,
            str(moa_execute_path()),
            "--payload-file",
            str(_CLEAR_DISPATCH_TPL),
            "--family-fund-reward-dispatch-clear",
            "--family-fund-week",
            target_monday,
            "--family-fund-week-offset",
            "0",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "清除家族基金奖励下发记录失败")[-600:])


def run_family_fund_reward_dispatch(
    *,
    offset: int = 0,
    extra: str = "",
    timeout_ms: int = 180000,
) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(moa_execute_path()),
            "--payload-file",
            str(_DISPATCH_TPL),
            "--family-fund-reward-dispatch-offset",
            str(offset),
            "--family-fund-reward-dispatch-extra",
            extra,
            "--timeout-ms",
            str(timeout_ms),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "家族基金奖励下发 MOA 失败")[-600:])
    text = proc.stdout
    try:
        body = json.loads(text[text.find("{") : text.rfind("}") + 1])
        inner = body.get("result") if isinstance(body.get("result"), dict) else {}
        inner_ec = int(inner.get("ec", 0))
        if inner_ec != 0:
            raise RuntimeError(f"家族基金奖励下发业务失败: ec={inner_ec}, em={inner.get('em')}")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法解析家族基金奖励下发返回: {exc}") from exc


async def load_calc_sheet_async(workbook: str) -> tuple[list[str], list[list[Any]]]:
    sheets = await fetch_workbook_sheets_async(workbook)
    matrix = sheets.get(CALC_SHEET) or sheets.get("应发钻测算") or []
    if len(matrix) < 2:
        raise RuntimeError(f"「{CALC_SHEET}」为空，请先执行家族基金数据落表")
    header = [_cell(matrix[0], i) for i in range(len(matrix[0]))]
    return header, matrix


def _diamond_verify_ok(expected: int, delta: int) -> bool:
    """实发与应发完全一致，或差 1 钻（服务端小数舍入与测算 floor 可能不一致）。"""
    return delta == expected or abs(delta - expected) == 1


def _diamond_verify_cells(expected: int, delta: int) -> tuple[str, str]:
    """返回 (验收, 备注)：验收仅「通过/不通过」，具体问题写备注。"""
    if _diamond_verify_ok(expected, delta):
        return "通过", ""
    return "不通过", f"期望{expected}实发{delta}"


def parse_expected_rows(header: list[str], matrix: list[list[Any]]) -> list[dict[str, Any]]:
    idx = {name: header.index(name) for name in header if name}
    rows: list[dict[str, Any]] = []
    for row in matrix[1:]:
        if _cell(row, 0) == "测试结果总结":
            break
        uid = _cell(row, idx.get("userId", 7))
        expected = _cell(row, idx.get("应发钻石", 13))
        if not uid.isdigit():
            continue
        if not expected or int(float(expected)) <= 0:
            continue
        rows.append(
            {
                "weekMonday": _cell(row, idx.get("周期", 0)),
                "familyId": _cell(row, idx.get("家族ID", 1)),
                "userId": uid,
                "expectedDiamond": int(float(expected)),
            }
        )
    if not rows:
        raise RuntimeError(f"「{CALC_SHEET}」无 应发钻石>0 的用户")
    return rows


def _parse_sheet_members(header: list[str], matrix: list[list[Any]]) -> tuple[int, list[dict[str, Any]]]:
    idx = {name: header.index(name) for name in header if name}
    pool = 0
    members: list[dict[str, Any]] = []
    for row in matrix[1:]:
        if _cell(row, 0) == "测试结果总结":
            break
        uid = _cell(row, idx.get("userId", 7))
        if not uid.isdigit():
            continue
        row_pool = _cell(row, idx.get("奖池钻石", 6))
        if row_pool.isdigit():
            pool = int(row_pool)
        contrib_raw = _cell(row, idx.get("成员贡献值", 10))
        members.append(
            {
                "userId": uid,
                "contribution": int(contrib_raw) if contrib_raw.isdigit() else 0,
            }
        )
    if pool <= 0 or not members:
        raise RuntimeError(f"「{CALC_SHEET}」无法解析奖池或成员行")
    return pool, members


async def _refresh_expected_by_uid_async(
    workbook: str,
    header: list[str],
    matrix: list[list[Any]],
) -> dict[str, dict[str, Any]]:
    from family_fund_calc_utils import fetch_family_fund_config  # noqa: PLC0415
    from mse_param_sheet_to_json import _parse_param_sheet  # noqa: PLC0415
    from mse_workbook_utils import (  # noqa: PLC0415
        apply_parsed_values_to_original,
        resolve_param_sheet_name,
    )

    pool, members = _parse_sheet_members(header, matrix)
    sheets = await fetch_workbook_sheets_async(workbook)
    sheet_name = resolve_param_sheet_name(sheets, None)
    parsed, _ = _parse_param_sheet(sheets[sheet_name])
    config = apply_parsed_values_to_original(fetch_family_fund_config(), parsed)
    min_rank = int(config.get("minContributionToRank") or 500)
    assign_contribution_ranks(members, min_contribution_to_rank=min_rank)
    expected_rows = compute_member_expected_diamonds(config=config, pool=pool, members=members)
    return {
        str(row["userId"]): {
            "expectedDiamond": int(row["expectedDiamond"]),
            "shareRatio": float(row["shareRatio"]),
            "rank": row.get("rank"),
        }
        for row in expected_rows
    }


def _parse_verified_rows_from_sheet(
    header: list[str],
    matrix: list[list[Any]],
    *,
    expected_by_uid: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    idx = {name: header.index(name) for name in header if name}
    rows: list[dict[str, Any]] = []
    for row in matrix[1:]:
        if _cell(row, 0) == "测试结果总结":
            break
        uid = _cell(row, idx.get("userId", 7))
        expected_raw = _cell(row, idx.get("应发钻石", 13))
        delta_raw = _cell(row, idx.get("实际增量", 14))
        if not uid.isdigit() or not delta_raw:
            continue
        if expected_by_uid and uid in expected_by_uid:
            expected = int(expected_by_uid[uid]["expectedDiamond"])
        elif expected_raw:
            expected = int(float(expected_raw))
        else:
            continue
        if expected <= 0:
            continue
        rows.append(
            {
                "userId": uid,
                "expectedDiamond": expected,
                "delta": int(float(delta_raw)),
            }
        )
    if not rows:
        raise RuntimeError(f"「{CALC_SHEET}」无已填实际增量的验收行，无法仅重算")
    return rows


def _build_verify_by_uid_from_deltas(rows: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], int, int, int, bool]:
    verify_by_uid: dict[str, dict[str, Any]] = {}
    pass_count = 0
    actual_total = 0
    expected_total = 0
    for item in rows:
        uid = item["userId"]
        expected = int(item["expectedDiamond"])
        delta = int(item["delta"])
        ok = _diamond_verify_ok(expected, delta)
        verdict, remark = _diamond_verify_cells(expected, delta)
        if ok:
            pass_count += 1
        expected_total += expected
        actual_total += delta
        verify_by_uid[uid] = {
            "delta": delta,
            "verdict": verdict,
            "remark": remark,
        }
    all_pass = pass_count == len(rows)
    return verify_by_uid, pass_count, expected_total, actual_total, all_pass


async def reformat_verify_from_sheet_async(workbook: str, *, week_monday: str) -> dict[str, Any]:
    week_monday = normalize_week_monday(week_monday)
    header, matrix = await load_calc_sheet_async(workbook)
    expected_by_uid = await _refresh_expected_by_uid_async(workbook, header, matrix)
    verified_rows = _parse_verified_rows_from_sheet(
        header,
        matrix,
        expected_by_uid=expected_by_uid,
    )
    verify_by_uid, pass_count, expected_total, actual_total, all_pass = _build_verify_by_uid_from_deltas(
        verified_rows
    )
    merged_rows = _merge_verify_into_calc_rows(
        matrix,
        verify_by_uid=verify_by_uid,
        expected_by_uid=expected_by_uid,
        pass_count=pass_count,
        verified_count=len(verified_rows),
        expected_total=expected_total,
        actual_total=actual_total,
        all_pass=all_pass,
    )
    workbook_id = node_id(workbook)
    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    await _write_sheet_replace(
        token=token,
        operator=operator,
        workbook_id=workbook_id,
        sheet_name=CALC_SHEET,
        rows=merged_rows,
    )
    await rename_family_fund_workbook_async(workbook, week_monday)
    url = f"https://alidocs.dingtalk.com/i/nodes/{workbook_id}"
    return {
        "workbookUrl": url,
        "sheetName": CALC_SHEET,
        "mode": "reformat_only",
        "verifiedUsers": len(verified_rows),
        "passCount": pass_count,
        "expectedTotalDiamonds": expected_total,
        "actualTotalDiamonds": actual_total,
        "allPass": all_pass,
    }


def reformat_verify_from_sheet(workbook: str, *, week_monday: str) -> dict[str, Any]:
    return asyncio.run(reformat_verify_from_sheet_async(workbook, week_monday=week_monday))


def _merge_verify_into_calc_rows(
    matrix: list[list[Any]],
    *,
    verify_by_uid: dict[str, dict[str, Any]],
    expected_by_uid: dict[str, dict[str, Any]] | None = None,
    pass_count: int,
    verified_count: int,
    expected_total: int,
    actual_total: int,
    all_pass: bool,
) -> list[list[str]]:
    width = len(FAMILY_FUND_TEST_HEADER)
    idx = {name: FAMILY_FUND_TEST_HEADER.index(name) for name in FAMILY_FUND_TEST_HEADER}
    old_header = [_cell(matrix[0], i) for i in range(len(matrix[0]))]
    old_idx = {name: i for i, name in enumerate(old_header) if name}
    out: list[list[str]] = [FAMILY_FUND_TEST_HEADER]

    for row in matrix[1:]:
        if _cell(row, 0) == "测试结果总结":
            break
        uid = _cell(row, old_idx.get("userId", 7))
        if not uid.isdigit():
            continue
        new_row = [""] * width
        for key in FAMILY_FUND_TEST_HEADER:
            if key in {"实际增量", "验收", "备注", "应发钻石", "分配比例", "榜单排名"}:
                continue
            if key in old_idx and key in idx:
                new_row[idx[key]] = _cell(row, old_idx[key])
        if expected_by_uid and uid in expected_by_uid:
            exp = expected_by_uid[uid]
            new_row[idx["应发钻石"]] = str(exp["expectedDiamond"])
            ratio = float(exp["shareRatio"])
            new_row[idx["分配比例"]] = f"{ratio:.6f}" if ratio else "0"
            rank = exp.get("rank")
            new_row[idx["榜单排名"]] = (
                str(rank) if rank is not None and int(rank) <= 30 else "30+"
            )
        elif "应发钻石" in old_idx:
            new_row[idx["应发钻石"]] = _cell(row, old_idx["应发钻石"])
            if "分配比例" in old_idx:
                new_row[idx["分配比例"]] = _cell(row, old_idx["分配比例"])
        if uid in verify_by_uid:
            v = verify_by_uid[uid]
            new_row[idx["实际增量"]] = str(v["delta"])
            new_row[idx["验收"]] = v["verdict"]
            new_row[idx["备注"]] = v.get("remark") or ""
        else:
            old_remark = _cell(row, old_idx.get("备注", -1))
            if old_remark and old_remark != "30+":
                new_row[idx["备注"]] = old_remark
        out.append([str(c) for c in new_row])

    out.append([""] * width)
    summary = [""] * width
    summary[0] = "测试结果总结"
    summary[idx["应发钻石"]] = str(expected_total)
    summary[idx["实际增量"]] = str(actual_total)
    summary[idx["验收"]] = "通过" if all_pass else "不通过"
    summary[idx["备注"]] = (
        f"应发合计={expected_total} 实发合计={actual_total} 通过={pass_count}/{verified_count}"
    )
    out.append([str(c) for c in summary])
    return out


async def dispatch_verify_async(
    workbook: str,
    *,
    week_monday: str,
    settle_expr: str = "",
    skip_settle: bool = False,
    dispatch_offset: int = 0,
    dispatch_extra: str = "",
    diamond_delay: float = 0.08,
) -> dict[str, Any]:
    week_monday = normalize_week_monday(week_monday)
    header, matrix = await load_calc_sheet_async(workbook)
    expected_rows = parse_expected_rows(header, matrix)
    user_ids = [r["userId"] for r in expected_rows]
    before = {uid: query_diamond(uid) for uid in user_ids}

    if not skip_settle:
        if settle_expr.strip():
            raise RuntimeError(
                "已登记 dispatchFamilyFundRewardTask，请用 --dispatch-offset 替代 --settle-expr"
            )
        run_family_fund_reward_dispatch_clear(
            week_monday=week_monday,
            dispatch_offset=dispatch_offset,
        )
        run_family_fund_reward_dispatch(offset=dispatch_offset, extra=dispatch_extra)
        time.sleep(2.0)

    verify_by_uid: dict[str, dict[str, Any]] = {}
    pass_count = 0
    actual_total = 0
    expected_total = sum(int(r["expectedDiamond"]) for r in expected_rows)

    for item in expected_rows:
        uid = item["userId"]
        after = query_diamond(uid)
        if diamond_delay > 0:
            time.sleep(diamond_delay)
        delta = after - before.get(uid, 0)
        expected = int(item["expectedDiamond"])
        ok = _diamond_verify_ok(expected, delta)
        verdict, remark = _diamond_verify_cells(expected, delta)
        if ok:
            pass_count += 1
        actual_total += delta
        verify_by_uid[uid] = {
            "before": before.get(uid, 0),
            "after": after,
            "delta": delta,
            "verdict": verdict,
            "remark": remark,
        }

    all_pass = pass_count == len(expected_rows)
    merged_rows = _merge_verify_into_calc_rows(
        matrix,
        verify_by_uid=verify_by_uid,
        pass_count=pass_count,
        verified_count=len(expected_rows),
        expected_total=expected_total,
        actual_total=actual_total,
        all_pass=all_pass,
    )

    workbook_id = node_id(workbook)
    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    await _write_sheet_replace(
        token=token,
        operator=operator,
        workbook_id=workbook_id,
        sheet_name=CALC_SHEET,
        rows=merged_rows,
    )
    await rename_family_fund_workbook_async(workbook, week_monday)
    url = f"https://alidocs.dingtalk.com/i/nodes/{workbook_id}"
    return {
        "workbookUrl": url,
        "sheetName": CALC_SHEET,
        "verifiedUsers": len(expected_rows),
        "passCount": pass_count,
        "expectedTotalDiamonds": expected_total,
        "actualTotalDiamonds": actual_total,
        "allPass": all_pass,
    }


def dispatch_verify(workbook: str, **kwargs: Any) -> dict[str, Any]:
    return asyncio.run(dispatch_verify_async(workbook, **kwargs))


def main() -> int:
    parser = argparse.ArgumentParser(description="家族基金发钻验收 → 回写家族基金测试单表")
    parser.add_argument("workbook")
    parser.add_argument("--week-monday", required=True)
    parser.add_argument(
        "--dispatch-offset",
        type=int,
        default=0,
        help="家族基金奖励下发周偏移（0=本周，-1=上周；dispatchFamilyFundRewardTask 参数1）",
    )
    parser.add_argument(
        "--dispatch-extra",
        default="",
        help="家族基金奖励下发参数2 string（默认空）",
    )
    parser.add_argument("--settle-expr", default="", help="已废弃，请用 --dispatch-offset")
    parser.add_argument("--skip-settle", action="store_true", help="仅查钻对比（已手动发奖）")
    parser.add_argument(
        "--reformat-only",
        action="store_true",
        help="按表中已有「实际增量」重算验收/备注并回写（不重复发奖、不查钻）",
    )
    args = parser.parse_args()
    try:
        if args.reformat_only:
            summary = reformat_verify_from_sheet(
                args.workbook.strip(),
                week_monday=args.week_monday.strip(),
            )
        else:
            summary = dispatch_verify(
                args.workbook.strip(),
                week_monday=args.week_monday.strip(),
                settle_expr=args.settle_expr.strip(),
                skip_settle=args.skip_settle,
                dispatch_offset=args.dispatch_offset,
                dispatch_extra=args.dispatch_extra.strip(),
            )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("allPass") else 2


if __name__ == "__main__":
    raise SystemExit(main())
