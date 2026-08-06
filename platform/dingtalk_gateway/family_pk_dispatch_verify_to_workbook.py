#!/usr/bin/env python3
"""第六步：清除结算记录 → 下发家族 PK 奖励 → 发奖前后查钻验收 → 新建 Sheet「发钻实发验收」。"""

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

from family_pk_calc_utils import rename_family_pk_workbook  # noqa: E402
from family_pk_member_reward_to_workbook import (  # noqa: E402
    compute_member_reward_rows,
    export_user_reward_contrib_verify_to_workbook,
)
from family_pk_tab_to_workbook import (  # noqa: E402
    DEFAULT_WORKBOOK,
    _ensure_sheet,
    _write_sheet_replace,
)
from mse_workbook_utils import node_id  # noqa: E402
from alidocs_excel_export import _excel_env, _get_token_and_operator  # noqa: E402

import httpx  # noqa: E402

DEFAULT_SHEET = "发钻实发验收"
DISPATCH_HEADER = [
    "PK日期",
    "家族ID",
    "家族名称",
    "成员userId",
    "手机号",
    "应发钻石",
    "发奖前钻石",
    "发奖后钻石",
    "实发钻石",
    "验收",
]

_SETTLE_TPL = moa_template("家族PK-结算发奖匹配.json")
_CLEAR_SETTLE_TPL = moa_template("家族PK-清除结算奖励.json")
_DIAMOND_TPL = moa_template("钻石-查询余额.json")


def _normalize_date(text: str) -> str:
    value = text.strip()
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return value
    raise ValueError(f"日期须为 yyyy-MM-dd: {text!r}")


def _next_day(pk_date: str) -> str:
    return (datetime.strptime(pk_date, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()


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
        raise RuntimeError((proc.stderr or proc.stdout or "查钻失败")[-500:])
    text = proc.stdout
    summary = json.loads(text[text.find("{") : text.rfind("}") + 1])
    return int(summary["diamonds"])


def batch_diamonds(user_ids: list[str], *, delay: float = 0.05) -> dict[str, int]:
    out: dict[str, int] = {}
    for i, uid in enumerate(user_ids):
        try:
            out[uid] = query_diamond(uid)
        except (RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            print(f"WARN 查钻失败 uid={uid}: {exc}", file=sys.stderr)
        if delay and i % 20 == 19:
            time.sleep(delay)
    return out


def _run_moa_payload(payload: Path, *, timeout_ms: int = 30000) -> dict[str, Any]:
    proc = subprocess.run(
        [
            sys.executable,
            str(moa_execute_path()),
            "--payload-file",
            str(payload),
            "--timeout-ms",
            str(timeout_ms),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=max(timeout_ms // 1000 + 60, 120),
        check=False,
    )
    text = (proc.stdout or proc.stderr or "").strip()
    if proc.returncode != 0:
        raise RuntimeError(text[-800:])
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return {"raw": text}
    return json.loads(text[start : end + 1])


def run_clear_settlement(pk_date: str, *, area: str = "MENA") -> dict[str, Any]:
    """清除 pkDate 结算发奖记录（resetSettleDataForTest），便于重复发奖验收。"""
    body = {"date": pk_date, "area": area, "rerunSettle": False}
    tpl = json.loads(_CLEAR_SETTLE_TPL.read_text(encoding="utf-8"))
    tpl["params"][0]["value"] = body
    tpl["params"][0]["json"] = json.dumps(body, ensure_ascii=False)
    payload = tmp_dir() / f"family_pk_clear_settle_{pk_date}.json"
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_text(json.dumps(tpl, ensure_ascii=False), encoding="utf-8")
    return _run_moa_payload(payload)


def run_settlement(settle_date: str, *, timeout_ms: int) -> dict[str, Any]:
    tpl = json.loads(_SETTLE_TPL.read_text(encoding="utf-8"))
    tpl["params"][0]["value"] = settle_date
    tpl["params"][0]["txt"] = settle_date
    tpl.setdefault("settings", {})["time"] = str(timeout_ms)
    payload = tmp_dir() / f"family_pk_settle_{settle_date}.json"
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_text(json.dumps(tpl, ensure_ascii=False), encoding="utf-8")
    return _run_moa_payload(payload, timeout_ms=timeout_ms)


def _verify_status(expected: int, before: int | None, after: int | None) -> tuple[str, int | None]:
    if before is None or after is None:
        return "查钻失败", None
    delta = after - before
    if expected == delta:
        return "通过", delta
    return "不一致", delta


def build_verify_sheet_rows(
    *,
    pk_date: str,
    settle_date: str,
    family_names: dict[str, str],
    member_phones: dict[tuple[str, str], str],
    member_rows: list[dict[str, Any]],
    before: dict[str, int],
    after: dict[str, int],
    verify_summary: dict[str, Any],
) -> list[list[Any]]:
    pass_count = verify_summary.get("passCount", 0)
    mismatch_count = verify_summary.get("mismatchCount", 0)
    expected_total = sum(int(r.get("expectedDiamond") or 0) for r in member_rows)
    actual_total = verify_summary.get("actualRewardTotal", 0)

    rows: list[list[Any]] = [
        [
            "验收摘要",
            f"PK日期={pk_date}",
            f"发奖任务入参={settle_date}",
            f"应发钻={expected_total}",
            f"实发钻合计={actual_total}",
            f"通过={pass_count}",
            f"不一致={mismatch_count}",
        ],
        [
            "规则说明",
            "先 resetSettleDataForTest(pkDate) 清除结算记录，再 runFamilyPkMatchTask(次日) 重新发奖",
            "实际增量=发奖后钻石-发奖前钻石",
            "应得钻石=0 且增量=0 记通过",
            "",
            "",
            "",
        ],
        [],
        DISPATCH_HEADER,
    ]
    for item in member_rows:
        fid = str(item.get("familyId") or "")
        uid = str(item.get("userId") or "")
        expected = int(item.get("expectedDiamond") or 0)
        b = before.get(uid)
        a = after.get(uid)
        status, delta = _verify_status(expected, b, a)
        rows.append(
            [
                pk_date,
                fid,
                family_names.get(fid, ""),
                uid,
                member_phones.get((fid, uid), ""),
                expected,
                "" if b is None else b,
                "" if a is None else a,
                "" if delta is None else delta,
                status,
            ]
        )
    return rows


async def write_dispatch_sheet_async(
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


def export_dispatch_verify_to_workbook(
    *,
    workbook: str,
    pk_date: str,
    settle_date: str | None,
    seed_report: Path | None,
    sheet_name: str,
    timeout_ms: int,
    skip_clear_settle: bool,
    skip_settle: bool,
    settle_wait_sec: float,
    area: str = "MENA",
    user_id: str = "100486375",
    skip_contrib_verify: bool = False,
) -> dict[str, Any]:
    pk_date = _normalize_date(pk_date)
    settle_input = settle_date or _next_day(pk_date)

    member_rows, family_names, member_phones = compute_member_reward_rows(
        workbook=workbook,
        pk_date=pk_date,
        seed_report=seed_report,
    )
    user_ids = sorted({str(r["userId"]) for r in member_rows if str(r.get("userId") or "").isdigit()})
    if not user_ids:
        raise RuntimeError("未解析到待验收用户")

    clear_response: dict[str, Any] | None = None
    settle_response: dict[str, Any] | None = None
    if not skip_settle and not skip_clear_settle:
        print(f"清除 {pk_date} 结算发奖数据（area={area}）…", file=sys.stderr)
        clear_response = run_clear_settlement(pk_date, area=area)
        inner_clear = clear_response.get("result", {}).get("result", clear_response.get("result", {}))
        print(f"清除结算返回: {json.dumps(inner_clear, ensure_ascii=False)[:400]}", file=sys.stderr)

    print(f"发奖前查钻 {len(user_ids)} 人…", file=sys.stderr)
    before = batch_diamonds(user_ids)

    if not skip_settle:
        print(f"执行 runFamilyPkMatchTask({settle_input}) 下发 {pk_date} 奖励…", file=sys.stderr)
        settle_response = run_settlement(settle_input, timeout_ms=timeout_ms)
        inner = settle_response.get("result", {}).get("result", settle_response.get("result", {}))
        print(f"结算返回: {json.dumps(inner, ensure_ascii=False)[:400]}", file=sys.stderr)
        if settle_wait_sec > 0:
            time.sleep(settle_wait_sec)

    print(f"发奖后查钻 {len(user_ids)} 人…", file=sys.stderr)
    after = batch_diamonds(user_ids)

    mismatches: list[dict[str, Any]] = []
    pass_count = 0
    actual_reward_total = 0
    for item in member_rows:
        uid = str(item["userId"])
        expected = int(item.get("expectedDiamond") or 0)
        b = before.get(uid)
        a = after.get(uid)
        status, delta = _verify_status(expected, b, a)
        if status == "通过":
            pass_count += 1
            if delta is not None and expected > 0:
                actual_reward_total += delta
        elif status == "不一致":
            mismatches.append(
                {
                    "userId": uid,
                    "familyId": item.get("familyId"),
                    "expected": expected,
                    "before": b,
                    "after": a,
                    "delta": delta,
                }
            )

    verify_summary = {
        "passCount": pass_count,
        "mismatchCount": len(mismatches),
        "actualRewardTotal": actual_reward_total,
        "mismatches": mismatches[:100],
    }

    sheet_rows = build_verify_sheet_rows(
        pk_date=pk_date,
        settle_date=settle_input,
        family_names=family_names,
        member_phones=member_phones,
        member_rows=member_rows,
        before=before,
        after=after,
        verify_summary=verify_summary,
    )
    doc_url = asyncio.run(
        write_dispatch_sheet_async(workbook, sheet_rows, sheet_name=sheet_name)
    )
    workbook_title = rename_family_pk_workbook(workbook, pk_date)

    summary = {
        "pkDate": pk_date,
        "settleInputDate": settle_input,
        "memberCount": len(member_rows),
        "expectedTotal": sum(int(r.get("expectedDiamond") or 0) for r in member_rows),
        "actualRewardTotal": actual_reward_total,
        "passCount": pass_count,
        "mismatchCount": len(mismatches),
        "skippedSettle": skip_settle,
        "skippedClearSettle": skip_clear_settle,
        "clearSettleResponse": clear_response,
        "settleResponse": settle_response,
        "verify": verify_summary,
        "workbookUrl": doc_url,
        "workbookTitle": workbook_title,
        "sheetName": sheet_name,
    }
    out_path = tmp_dir() / f"family_pk_dispatch_verify_{pk_date}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["reportPath"] = str(out_path)

    if not skip_contrib_verify:
        print("结算后发奖完成，开始 MOA 贡献榜验收并回写用户发钻测试…", file=sys.stderr)
        contrib_summary = export_user_reward_contrib_verify_to_workbook(
            workbook=workbook,
            pk_date=pk_date,
            user_id=str(user_id).strip(),
            seed_report=seed_report,
            area=area,
        )
        summary["contribVerify"] = contrib_summary.get("contribVerify")
        summary["userRewardSheetUrl"] = contrib_summary.get("workbookUrl")

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="家族 PK 发奖验收 → 钉钉「发钻实发验收」")
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK)
    parser.add_argument("--pk-date", required=True, help="匹配日期 yyyy-MM-dd")
    parser.add_argument(
        "--settle-date",
        help="runFamilyPkMatchTask 入参（默认 pk-date 次日，对 pk-date 发奖）",
    )
    parser.add_argument("--seed-report", type=Path, help="第五步造数报告路径")
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET)
    parser.add_argument("--timeout-ms", type=int, default=180000)
    parser.add_argument("--settle-wait-sec", type=float, default=5.0, help="发奖后等待秒数再查钻")
    parser.add_argument("--area", default="MENA", help="清除结算奖励大区")
    parser.add_argument(
        "--user-id",
        "--momoid",
        dest="user_id",
        default="100486375",
        help="MOA getFamilyPkUserList 请求 userId（贡献榜验收）",
    )
    parser.add_argument("--skip-contrib-verify", action="store_true", help="跳过结算后贡献榜验收")
    parser.add_argument("--skip-clear-settle", action="store_true", help="跳过清除结算记录，直接发奖")
    parser.add_argument("--skip-settle", action="store_true", help="仅查钻对比，不调用发奖")
    args = parser.parse_args()

    try:
        summary = export_dispatch_verify_to_workbook(
            workbook=args.workbook.strip(),
            pk_date=args.pk_date.strip(),
            settle_date=(args.settle_date.strip() if args.settle_date else None),
            seed_report=args.seed_report,
            sheet_name=args.sheet_name.strip() or DEFAULT_SHEET,
            timeout_ms=args.timeout_ms,
            skip_clear_settle=args.skip_clear_settle,
            skip_settle=args.skip_settle,
            settle_wait_sec=args.settle_wait_sec,
            area=args.area.strip() or "MENA",
            user_id=str(args.user_id).strip(),
            skip_contrib_verify=args.skip_contrib_verify,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
