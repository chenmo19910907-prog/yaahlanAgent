#!/usr/bin/env python3
"""单账号直接在自己房间砸蛋，逐组验收钻石到账并落表。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
GATEWAY_DIR = REPO_ROOT / "platform" / "dingtalk_gateway"
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
if str(REPO_ROOT / "MOA") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "MOA"))
if str(REPO_ROOT / "Gift") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "Gift"))

from anniversary_egg_smash_to_workbook import (  # noqa: E402
    DEFAULT_SHEET,
    append_smash_record_async,
    evaluate_diamond_credit,
    expected_diamond_delta_from_smash,
    expected_vip_exp_delta_from_smash,
    load_activity_rules,
    record_to_row,
)
from moa.anniversary_egg import (  # noqa: E402
    get_egg_home,
    resolve_own_room_id,
    smash_egg_once,
)
from gift.send_stage import query_diamond_balance, query_vip_exp  # noqa: E402

DEFAULT_WORKBOOK = (
    "https://alidocs.dingtalk.com/i/nodes/jb9Y4gmKWr7wodldC4ow9vLPVGXn6lpz"
)


def _run_json(cmd: list[str], *, timeout: int = 120) -> dict[str, Any]:
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    text = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError(f"命令无 JSON: {' '.join(cmd)} :: {text[-400:]}")
    data = json.loads(text[start : end + 1])
    if proc.returncode != 0 and not data.get("ok") and "userId" not in data:
        raise RuntimeError(f"命令失败 exit={proc.returncode}: {text[-400:]}")
    return data


def resolve_phone_user(phone: str) -> dict[str, str]:
    data = _run_json(
        [
            "python3",
            str(REPO_ROOT / "MOA/moa_execute.py"),
            "--payload-file",
            str(REPO_ROOT / "MOA/templates/用户-按手机号查userId.json"),
            "--query-user-by-phone",
            phone,
        ]
    )
    uid = str(data.get("userId") or data.get("data") or "").strip()
    if not uid:
        raise RuntimeError(f"手机号 {phone} 未解析到 userId: {data}")
    room = resolve_own_room_id(uid)
    return {"phone": phone, "userId": uid, "roomId": room}


def _normalize_smash_prizes(smash: dict[str, Any]) -> dict[str, Any]:
    out = dict(smash)
    prizes = out.get("prizes")
    if out.get("rewards") is None and isinstance(prizes, list):
        out["rewards"] = [
            {
                "name": p.get("prizeName") or p.get("name") or p.get("prizeId") or "奖励",
                "num": p.get("num") or p.get("count") or p.get("amount") or 1,
                "prizeId": p.get("prizeId"),
                "prizeType": p.get("prizeType"),
                "icon": p.get("icon"),
            }
            for p in prizes
            if isinstance(p, dict)
        ]
    return out


def query_balance_after_credit(
    user_id: str,
    *,
    before: int,
    expected_delta: int,
    query_fn,
    timeout_s: float = 8.0,
) -> int:
    if expected_delta <= 0:
        return query_fn(user_id)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        bal = query_fn(user_id)
        if bal - before >= expected_delta:
            return bal
        time.sleep(0.35)
    return query_fn(user_id)


def _append_with_retry(
    workbook: str,
    row: list[str],
    *,
    sheet_name: str,
    attempts: int = 4,
) -> None:
    last_exc: BaseException | None = None
    for i in range(max(1, attempts)):
        try:
            asyncio.run(
                append_smash_record_async(workbook, row, sheet_name=sheet_name)
            )
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            wait_s = min(2**i, 12)
            print(
                f"  写表失败 ({i + 1}/{attempts}): {exc}；{wait_s}s 后重试",
                file=sys.stderr,
            )
            time.sleep(wait_s)
    assert last_exc is not None
    raise last_exc


def run_one(
    *,
    case_no: int,
    account: dict[str, str],
    workbook: str,
    smash_sheet: str,
    dry_run: bool,
) -> dict[str, Any]:
    phone = account["phone"]
    user_id = account["userId"]
    room_id = account["roomId"]

    remain = int(
        get_egg_home(user_id, room_id).get("remainChances") or 0
    )
    diamond_before = query_diamond_balance(user_id)
    vip_before = query_vip_exp(user_id)

    print(
        f"[{case_no}] phone={phone} user={user_id} room={room_id} "
        f"remain={remain} diamond={diamond_before} vipExp={vip_before}",
        file=sys.stderr,
    )

    if remain <= 0:
        diamond_check = evaluate_diamond_credit(
            before=diamond_before,
            after=diamond_before,
            expected=0,
        )
        vip_check = evaluate_diamond_credit(
            before=vip_before,
            after=vip_before,
            expected=0,
        )
        out = {
            "caseNo": case_no,
            "phone": phone,
            "userId": user_id,
            "roomId": room_id,
            "remainBefore": remain,
            "diamond": diamond_check,
            "vipExp": vip_check,
            "smash": {"skipReason": "remainChances=0", "smashCount": 0},
            "verdict": "跳过：无砸蛋次数",
        }
        return out

    smash = _normalize_smash_prizes(
        smash_egg_once(user_id=user_id, room_id=room_id, lang="en")
    )
    expected_diamond = expected_diamond_delta_from_smash(smash)
    expected_vip = expected_vip_exp_delta_from_smash(smash)
    diamond_after = query_balance_after_credit(
        user_id,
        before=diamond_before,
        expected_delta=expected_diamond,
        query_fn=query_diamond_balance,
    )
    vip_after = query_balance_after_credit(
        user_id,
        before=vip_before,
        expected_delta=expected_vip,
        query_fn=query_vip_exp,
    )
    diamond_check = evaluate_diamond_credit(
        before=diamond_before,
        after=diamond_after,
        expected=expected_diamond,
    )
    vip_check = evaluate_diamond_credit(
        before=vip_before,
        after=vip_after,
        expected=expected_vip,
    )

    print(
        f"  smash count={smash.get('smashCount')} "
        f"expectedDiamond={expected_diamond} diamond {diamond_before}→{diamond_after} "
        f"delta={diamond_check['actualDelta']} | "
        f"expectedVip={expected_vip} vip {vip_before}→{vip_after} "
        f"delta={vip_check['actualDelta']}",
        file=sys.stderr,
    )

    verify_payload: dict[str, Any] = {
        "caseNo": case_no,
        "phone": phone,
        "userId": user_id,
        "roomId": room_id,
        "gainedChances": 0,
        "diamondBefore": diamond_before,
        "diamondAfter": diamond_after,
        "expectedDiamond": expected_diamond,
        "actualDiamondDelta": diamond_check.get("actualDelta"),
        "vipExpBefore": vip_before,
        "vipExpAfter": vip_after,
        "expectedVipExp": expected_vip,
        "actualVipExpDelta": vip_check.get("actualDelta"),
    }

    row = record_to_row(
        smash,
        fallback_user_id=user_id,
        fallback_room_id=room_id,
        fallback_smash_count=smash.get("smashCount"),
        verify=verify_payload,
    )
    verdict = str(row[-2] or "").strip()

    out = {
        "caseNo": case_no,
        "phone": phone,
        "userId": user_id,
        "roomId": room_id,
        "remainBefore": smash.get("remainBefore"),
        "remainAfter": smash.get("remainAfter"),
        "diamond": diamond_check,
        "vipExp": vip_check,
        "expectedDiamond": expected_diamond,
        "expectedVipExp": expected_vip,
        "smash": smash,
        "verdict": verdict,
    }

    if dry_run:
        print(f"  dry-run verdict={verdict}", file=sys.stderr)
        return out

    try:
        _append_with_retry(workbook, row, sheet_name=smash_sheet)
    except Exception as write_exc:
        out["writeFailed"] = True
        out["writeError"] = str(write_exc)
        print(f"  写表失败 case={case_no}: {write_exc}", file=sys.stderr)
        return out

    print(f"  已实时落表 case={case_no} verdict={verdict}", file=sys.stderr)
    return out


def _build_batch_result_markdown(
    *,
    phone: str,
    account: dict[str, str],
    summary: dict[str, int],
    initial_balance: int,
    final_balance: int,
    workbook: str,
    fail_details: list[str],
) -> str:
    total = int(summary.get("total") or 0)
    passed = int(summary.get("pass") or 0)
    failed = int(summary.get("fail") or 0)
    skipped = int(summary.get("skip") or 0)
    errors = int(summary.get("error") or 0)
    pass_rate = f"{passed * 100 / total:.1f}%" if total else "0%"
    lines = [
        "## 砸金蛋直接砸蛋 · 钻石/VIP 经验到账验收",
        "",
        f"- 测试账号：**{phone}**（userId `{account.get('userId')}`，房间 `{account.get('roomId')}`）",
        f"- 测试前钻石余额：**{initial_balance:,}** → 测试后：**{final_balance:,}**（净变动 **{final_balance - initial_balance:+,}**）",
        f"- 测试组数：**{total}**（不下发获次，直接在自己房间砸蛋）",
        f"- 钻石到账通过：**{passed}**，失败：**{failed}**，跳过：**{skipped}**，错误：**{errors}**，通过率 **{pass_rate}**",
        f"- 记录表：[砸金蛋测试记录]({workbook})",
        "",
        "### 验收说明",
        "",
        "每组砸蛋前后查询钻石余额与 VIP 经验值，与本次奖励中钻石/VIP 经验数量（含神秘奖励）比对，一致则通过。",
    ]
    if fail_details:
        lines.extend(["", "### 未通过/异常明细", ""])
        for item in fail_details[:25]:
            lines.append(f"- {item}")
        if len(fail_details) > 25:
            lines.append(f"- …另有 {len(fail_details) - 25} 条")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="直接砸蛋并验收钻石到账")
    parser.add_argument("--phone", required=True)
    parser.add_argument("--rounds", type=int, default=30)
    parser.add_argument("--start-case", type=int, default=1)
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK)
    parser.add_argument("--smash-sheet", default=DEFAULT_SHEET)
    parser.add_argument("--user-key", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--progress-file",
        default=str(REPO_ROOT / ".tmp" / "anniversary_egg_direct_diamond_progress.jsonl"),
    )
    args = parser.parse_args()

    if args.rounds <= 0:
        raise SystemExit("rounds 须为正整数")

    account = resolve_phone_user(args.phone.strip())
    initial_balance = query_diamond_balance(account["userId"])
    print(
        f"账号 {account['phone']} → {account['userId']} room={account['roomId']} "
        f"初始钻石={initial_balance}",
        file=sys.stderr,
    )

    rules = load_activity_rules(force_refresh=True)
    print(f"rules={rules}", file=sys.stderr)
    progress = Path(args.progress_file)
    progress.parent.mkdir(parents=True, exist_ok=True)

    summary = {"pass": 0, "fail": 0, "skip": 0, "error": 0, "total": args.rounds}
    fail_details: list[str] = []

    def _report_progress(current: int, *, result_text: str = "") -> None:
        if not args.user_key or args.rounds < 3:
            return
        cmd = [
            "python3",
            str(REPO_ROOT / "platform/dingtalk_gateway/batch_progress_report.py"),
            "--user-key",
            args.user_key,
            "--current",
            str(current),
            "--total",
            str(args.rounds),
            "--label",
            "砸蛋到账验收",
        ]
        if current > 0:
            cmd.extend(["--detail", f"第{current}组"])
        if result_text:
            cmd.extend(["--result-text", result_text])
        subprocess.run(cmd, cwd=str(REPO_ROOT), check=False)

    _report_progress(0)

    for i in range(args.rounds):
        case_no = args.start_case + i
        try:
            result = run_one(
                case_no=case_no,
                account=account,
                workbook=args.workbook,
                smash_sheet=args.smash_sheet,
                dry_run=args.dry_run,
            )
            verdict = str(result.get("verdict") or "")
            if result.get("writeFailed"):
                summary["error"] += 1
                fail_details.append(
                    f"第{case_no}组：写表失败（{result.get('writeError', '')[:80]}）"
                )
            elif verdict.startswith("跳过"):
                summary["skip"] += 1
            elif verdict == "通过":
                summary["pass"] += 1
            else:
                summary["fail"] += 1
                d = result.get("diamond") or {}
                fail_details.append(
                    f"第{case_no}组：{verdict} "
                    f"(预期+{d.get('expectedDelta', result.get('expectedDiamond', '?'))}钻，"
                    f"实际+{d.get('actualDelta', '?')}钻)"
                )

            with progress.open("a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
                f.flush()
            print(
                f"  >> case={case_no} verdict={verdict} "
                f"累计 pass={summary['pass']} fail={summary['fail']} "
                f"skip={summary['skip']} err={summary['error']}",
                file=sys.stderr,
                flush=True,
            )
            _report_progress(i + 1)
        except Exception as exc:  # noqa: BLE001
            summary["error"] += 1
            fail_details.append(f"第{case_no}组：错误（{str(exc)[:120]}）")
            err = {"caseNo": case_no, "verdict": "错误", "error": str(exc)}
            with progress.open("a", encoding="utf-8") as f:
                f.write(json.dumps(err, ensure_ascii=False) + "\n")
                f.flush()
            print(f"  ERROR case={case_no}: {exc}", file=sys.stderr)
            _report_progress(i + 1)

    final_balance = query_diamond_balance(account["userId"])
    if args.user_key and args.rounds >= 3:
        _report_progress(
            args.rounds,
            result_text=_build_batch_result_markdown(
                phone=args.phone,
                account=account,
                summary=summary,
                initial_balance=initial_balance,
                final_balance=final_balance,
                workbook=args.workbook,
                fail_details=fail_details,
            ),
        )

    out = {
        "phone": args.phone,
        "account": account,
        "initialBalance": initial_balance,
        "finalBalance": final_balance,
        "summary": summary,
        "workbookUrl": args.workbook,
        "progressFile": str(progress),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if summary["error"] == 0 and summary["fail"] == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
