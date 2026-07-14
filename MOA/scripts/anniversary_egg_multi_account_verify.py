#!/usr/bin/env python3
"""多账号自送获次 → 随机房间砸蛋 → 写入「砸金蛋测试记录」（含验收列）。

手机号账号自送 giftIds 礼物获次（随机 1~15），钻石不足充 100 万；
在账号房间中随机选房砸一次；对照配置验收并落表。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
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
    evaluate_acceptance_verdict,
    format_mystery_cell,
    load_activity_rules,
    normalize_room_smash_lifetime,
    record_to_row,
    resolve_egg_level_label,
    theory_mystery_tags,
    _reward_summary,
)
from moa.anniversary_egg import (  # noqa: E402
    expected_batch_from_remain,
    get_egg_home,
    get_room_egg_entry,
    resolve_own_room_id,
    smash_egg_once,
)

# fix import - smash result normalization lives in record script
from gift.send_stage import (  # noqa: E402
    StageGiftError,
    provide_diamond,
    query_diamond_balance,
    query_gift,
)

DEFAULT_WORKBOOK = (
    "https://alidocs.dingtalk.com/i/nodes/jb9Y4gmKWr7wodldC4ow9vLPVGXn6lpz"
)
DEFAULT_PHONES = [
    "13311111121",
    "13311111122",
    "13311111123",
    "13311111124",
    "13311111125",
]
GIFT_LIPSTICK = "2005057191"  # 199 钻，可堆叠折算获次
DIAMOND_PER_CHANCE = 500
TOP_UP_DIAMONDS = 1_000_000


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


def snap(user_id: str, room_id: str) -> dict[str, int]:
    home = get_egg_home(user_id, room_id)
    entry = get_room_egg_entry(user_id, room_id)
    return {
        "remain": int(home.get("remainChances") or entry.get("userRemainChances") or 0),
        "used": int(home.get("usedSmashChances") or 0),
        "roomSmash": int(entry.get("smashCount") or 0),
    }


def ensure_diamonds(user_id: str, need: int) -> int:
    """余额不足则充 100 万钻；返回本次充值数量。"""
    bal = query_diamond_balance(user_id)
    if bal >= need:
        return 0
    provide_diamond(user_id, TOP_UP_DIAMONDS)
    bal2 = query_diamond_balance(user_id)
    if bal2 < need:
        raise RuntimeError(f"充值后仍不足: user={user_id} bal={bal2} need={need}")
    return TOP_UP_DIAMONDS


def self_gift_for_chances(
    *,
    user_id: str,
    room_id: str,
    target_chances: int,
) -> dict[str, Any]:
    """自送 lipstick 堆钻获次；返回 gift 审计信息。"""
    gift_meta = query_gift(GIFT_LIPSTICK)
    unit = int(round(float(gift_meta.get("price") or 199)))
    diamonds_needed = max(1, int(target_chances)) * DIAMOND_PER_CHANCE
    gift_num = max(1, math.ceil(diamonds_needed / unit))
    cost = unit * gift_num
    topped = ensure_diamonds(user_id, cost)

    before = snap(user_id, room_id)
    cmd = [
        "python3",
        str(REPO_ROOT / "Gift/gift_execute.py"),
        "--scene",
        "chatroom",
        "--sender",
        user_id,
        "--receivers",
        user_id,
        "--gift-id",
        GIFT_LIPSTICK,
        "--scene-id",
        room_id,
        "--num",
        str(gift_num),
    ]
    # gift_execute 自身也会按 cost 补钻；我们已预充 100 万
    gift_out = _run_json(cmd, timeout=180)
    if not gift_out.get("ok"):
        raise RuntimeError(f"送礼失败: {gift_out}")

    # 送礼后次数可能短暂延迟，轮询几次
    gained = 0
    after = before
    for _ in range(8):
        time.sleep(0.4)
        after = snap(user_id, room_id)
        gained = after["remain"] - before["remain"]
        if gained > 0 or after["remain"] > 0:
            break

    return {
        "giftId": GIFT_LIPSTICK,
        "giftName": gift_meta.get("productName") or "lipstick",
        "giftNum": gift_num,
        "cost": cost,
        "topUpDiamonds": topped,
        "targetChances": target_chances,
        "gainedChances": max(0, gained),
        "remainBefore": before["remain"],
        "remainAfter": after["remain"],
        "usedBefore": before["used"],
        "usedAfter": after["used"],
    }


def _append_with_retry(coro_factory, *, attempts: int = 4) -> str:
    last: BaseException | None = None
    for i in range(max(1, attempts)):
        try:
            return asyncio.run(coro_factory())
        except Exception as exc:  # noqa: BLE001
            last = exc
            wait_s = min(2**i, 12)
            print(f"  写表失败 ({i + 1}/{attempts}): {exc}；{wait_s}s 后重试", file=sys.stderr)
            time.sleep(wait_s)
    assert last is not None
    raise last


def evaluate_case(
    *,
    smash: dict[str, Any],
    rules: dict[str, Any],
) -> dict[str, Any]:
    remain_before = int(smash.get("remainBefore") or 0)
    actual_smash = int(smash.get("smashCount") or 0)
    expected_smash = expected_batch_from_remain(remain_before)

    # 房间内/用户/平台 + 神秘保底：一律 year3Dao.testGetMysteryCount
    myst_b = smash.get("mysteryCountBefore") if isinstance(smash.get("mysteryCountBefore"), dict) else None
    myst_a = smash.get("mysteryCountAfter") if isinstance(smash.get("mysteryCountAfter"), dict) else None
    if myst_b and myst_a:
        user_before = int(myst_b.get("user") or 0)
        user_after = int(myst_a.get("user") or 0)
        myst_room_before = int(myst_b.get("room") or 0)
        myst_room_after = int(myst_a.get("room") or 0)
        plat_before_i = int(myst_b.get("platform") or 0)
        plat_after_i = int(myst_a.get("platform") or 0)
        room_after = myst_room_after
    else:
        egg_before_raw = smash.get("roomEggSmashBefore")
        if egg_before_raw is None:
            egg_before_raw = smash.get("roomSmashBefore")
        egg_after_raw = smash.get("roomEggSmashAfter")
        if egg_after_raw is None:
            egg_after_raw = smash.get("roomSmashCount")
        if egg_after_raw is None:
            egg_after_raw = smash.get("roomSmashAfter")
        room_before, room_after, _ = normalize_room_smash_lifetime(
            egg_before_raw, egg_after_raw, actual_smash
        )
        user_after = int(smash.get("userSmashCount") or smash.get("usedSmashAfter") or 0)
        user_before = int(
            smash.get("userSmashBefore")
            or smash.get("usedSmashBefore")
            or max(0, user_after - actual_smash)
        )
        myst_room_before = int(smash.get("mysteryRoomBefore") or room_before)
        myst_room_after = int(smash.get("mysteryRoomAfter") or room_after)
        plat_after = smash.get("platformSmashCount")
        try:
            plat_after_i = int(plat_after) if plat_after not in (None, "") else None
        except (TypeError, ValueError):
            plat_after_i = None
        plat_before_raw = smash.get("platformSmashBefore")
        try:
            plat_before_i = (
                int(plat_before_raw)
                if plat_before_raw not in (None, "")
                else (
                    max(0, plat_after_i - actual_smash)
                    if plat_after_i is not None
                    else None
                )
            )
        except (TypeError, ValueError):
            plat_before_i = None

    expected_level = resolve_egg_level_label(
        room_smash_lifetime=myst_room_after if myst_a else room_after,
        egg_level=smash.get("eggLevel"),
        rules=rules,
    )
    tags = theory_mystery_tags(
        user_before=user_before,
        user_after=user_after,
        room_before=myst_room_before,
        room_after=myst_room_after,
        platform_before=plat_before_i,
        platform_after=plat_after_i,
        rules=rules,
    )
    expected_mystery = "+".join(tags) if tags else ""
    actual_mystery_prizes = _reward_summary(
        smash.get("mysteryPrizes") or smash.get("mysteryRewards") or []
    )
    actual_mystery_cell = format_mystery_cell(actual_mystery_prizes, tags)
    tier = _reward_summary(smash.get("rewards") or smash.get("prizes") or [])

    acceptance = evaluate_acceptance_verdict(
        theory_tags=tags,
        mystery_cell=actual_mystery_cell,
        tier_cell=tier,
        batch=actual_smash,
        egg_level=expected_level,
        expected_batch=expected_smash,
        room_before=myst_room_before,
        room_after=myst_room_after,
        user_before=user_before,
        user_after=user_after,
        platform_before=plat_before_i,
        platform_after=plat_after_i,
    )
    checks: list[dict[str, Any]] = [
        {
            "item": "本次砸蛋次数",
            "pass": acceptance.get("smashCountOk", True),
            "expected": expected_smash,
            "actual": actual_smash,
        },
        {
            "item": "房/用/平累加",
            "pass": acceptance.get("countAccumOk", True),
            "expected": (
                f"房{myst_room_before}+{actual_smash}="
                f"{myst_room_before + actual_smash}；"
                f"用{user_before}+{actual_smash}={user_before + actual_smash}；"
                f"平"
                f"{(str(plat_before_i) + '+' + str(actual_smash) + '=' + str((plat_before_i or 0) + actual_smash)) if plat_before_i is not None else '跳过'}"
            ),
            "actual": (
                f"房{myst_room_after}；用{user_after}；"
                f"平{plat_after_i if plat_after_i is not None else '无'}"
            ),
        },
        {
            "item": "神秘奖励",
            "pass": acceptance["mysteryOk"],
            "expected": expected_mystery or "(无保底)",
            "actual": actual_mystery_cell or "(空)",
        },
        {
            "item": "金蛋等级礼物",
            "pass": acceptance["tierOk"],
            "expected": f"{expected_level}档次奖励非空",
            "actual": tier or "(空)",
        },
    ]
    failed = [c["item"] for c in checks if not c["pass"]]
    return {
        "expectedSmashCount": expected_smash,
        "actualSmashCount": actual_smash,
        "expectedEggLevel": expected_level,
        "actualEggLevel": expected_level,
        "expectedMystery": expected_mystery,
        "actualMystery": actual_mystery_cell,
        "tierReward": tier,
        "verdict": acceptance["verdict"],
        "failItems": acceptance["failItems"],
        "checks": checks,
        "failCheckItems": failed,
    }


def drain_remain_chances(
    user_id: str,
    room_id: str,
    *,
    max_calls: int = 80,
) -> dict[str, int]:
    """砸掉账号剩余次数（不落表），保证后续「只下发 N 次」后本次砸蛋次数≈N。"""
    before = snap(user_id, room_id)["remain"]
    calls = 0
    while calls < max_calls:
        cur = snap(user_id, room_id)
        if cur["remain"] <= 0:
            break
        smash_egg_once(user_id=user_id, room_id=room_id, lang="en")
        calls += 1
        time.sleep(0.15)
    after = snap(user_id, room_id)["remain"]
    return {"remainBefore": before, "remainAfter": after, "drainCalls": calls}


def run_one(
    *,
    case_no: int,
    accounts: list[dict[str, str]],
    workbook: str,
    smash_sheet: str,
    dry_run: bool,
    rules: dict[str, Any],
    chance_min: int = 1,
    chance_max: int = 15,
    drain_remain: bool = False,
) -> dict[str, Any]:
    actor = random.choice(accounts)
    smash_room = random.choice(accounts)["roomId"]
    lo = min(int(chance_min), int(chance_max))
    hi = max(int(chance_min), int(chance_max))
    target = random.randint(lo, hi)
    phone = actor["phone"]
    user_id = actor["userId"]
    gift_room = actor["roomId"]

    print(
        f"[{case_no}] phone={phone} user={user_id} giftRoom={gift_room} "
        f"smashRoom={smash_room} targetChances={target}",
        file=sys.stderr,
    )

    drain_info: dict[str, int] | None = None
    if drain_remain:
        drain_info = drain_remain_chances(user_id, gift_room)
        print(
            f"  drain remain {drain_info['remainBefore']}→{drain_info['remainAfter']} "
            f"calls={drain_info['drainCalls']}",
            file=sys.stderr,
        )

    gift_info = self_gift_for_chances(
        user_id=user_id, room_id=gift_room, target_chances=target
    )
    print(
        f"  gift num={gift_info['giftNum']} topUp={gift_info['topUpDiamonds']} "
        f"remain {gift_info['remainBefore']}→{gift_info['remainAfter']} "
        f"gained={gift_info['gainedChances']}",
        file=sys.stderr,
    )

    # 砸蛋前再读一次剩余（以砸蛋房间视角）
    pre = snap(user_id, smash_room)
    if pre["remain"] <= 0:
        # 获次未到账时再等一会
        for _ in range(5):
            time.sleep(0.5)
            pre = snap(user_id, smash_room)
            if pre["remain"] > 0:
                break

    smash = smash_egg_once(user_id=user_id, room_id=smash_room, lang="en")
    # 轻量归一 prizes→rewards
    if smash.get("rewards") is None and isinstance(smash.get("prizes"), list):
        smash["rewards"] = [
            {
                "name": p.get("prizeName") or p.get("name") or p.get("prizeId") or "奖励",
                "num": p.get("num") or 1,
                "prizeId": p.get("prizeId"),
                "prizeType": p.get("prizeType"),
                "icon": p.get("icon"),
            }
            for p in smash["prizes"]
            if isinstance(p, dict)
        ]

    print(
        f"  smash remain {smash.get('remainBefore')}→{smash.get('remainAfter')} "
        f"count={smash.get('smashCount')} room={smash.get('roomSmashBefore')}→"
        f"{smash.get('roomSmashAfter')}",
        file=sys.stderr,
    )

    eval_out = evaluate_case(smash=smash, rules=rules)
    verify_payload = {
        "caseNo": case_no,
        "phone": phone,
        "userId": user_id,
        "roomId": smash_room,
        "targetChances": target,
        "gainedChances": gift_info["gainedChances"],
        "topUpDiamonds": gift_info["topUpDiamonds"],
        **eval_out,
    }
    row_smash = record_to_row(
        smash,
        fallback_user_id=user_id,
        fallback_room_id=smash_room,
        fallback_smash_count=smash.get("smashCount"),
        verify=verify_payload,
    )

    out = {
        "caseNo": case_no,
        "phone": phone,
        "userId": user_id,
        "giftRoomId": gift_room,
        "smashRoomId": smash_room,
        "gift": gift_info,
        "drain": drain_info,
        "smash": smash,
        "eval": eval_out,
        "verdict": eval_out["verdict"],
    }

    if dry_run:
        print(f"  dry-run verdict={eval_out['verdict']}", file=sys.stderr)
        return out

    try:
        _append_with_retry(
            lambda: append_smash_record_async(
                workbook, row_smash, sheet_name=smash_sheet
            )
        )
    except Exception as write_exc:
        # 写表失败仍返回完整 smash，便于事后补写；不抛异常以免丢掉结果
        out["writeFailed"] = True
        out["writeError"] = str(write_exc)
        print(
            f"  写表失败 case={case_no}: {write_exc}",
            file=sys.stderr,
        )
        return out
    print(f"  已实时落表 case={case_no} verdict={eval_out['verdict']}", file=sys.stderr)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="多账号砸金蛋批量验收（含验收结果落表）")
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK)
    parser.add_argument("--phones", default=",".join(DEFAULT_PHONES))
    parser.add_argument("--rounds", type=int, default=1000, help="测试组数")
    parser.add_argument("--start-case", type=int, default=1, help="起始用例序号")
    parser.add_argument(
        "--chance-min", type=int, default=1, help="自送获次随机下限（含）"
    )
    parser.add_argument(
        "--chance-max", type=int, default=15, help="自送获次随机上限（含）"
    )
    parser.add_argument(
        "--drain-remain",
        action="store_true",
        help="获次前先砸光剩余次数，保证「只下发 N 次」后本次砸蛋≈N",
    )
    parser.add_argument("--smash-sheet", default=DEFAULT_SHEET)
    parser.add_argument(
        "--verify-sheet",
        default=DEFAULT_SHEET,
        help="已废弃：验收列并入砸金蛋测试记录，此参数忽略",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--progress-file",
        default=str(REPO_ROOT / ".tmp" / "anniversary_egg_batch_progress.jsonl"),
    )
    args = parser.parse_args()

    phones = [p.strip() for p in args.phones.split(",") if p.strip()]
    if not phones:
        raise SystemExit("phones 为空")
    if args.rounds <= 0:
        raise SystemExit("rounds 须为正整数")
    if args.chance_min <= 0 or args.chance_max <= 0:
        raise SystemExit("chance-min/max 须为正整数")

    print("解析账号…", file=sys.stderr)
    accounts = [resolve_phone_user(p) for p in phones]
    for a in accounts:
        print(f"  {a['phone']} → {a['userId']} room={a['roomId']}", file=sys.stderr)

    rules = load_activity_rules(force_refresh=True)
    print(f"rules={rules}", file=sys.stderr)
    print(
        f"获次随机={args.chance_min}~{args.chance_max} rounds={args.rounds}",
        file=sys.stderr,
    )

    progress = Path(args.progress_file)
    progress.parent.mkdir(parents=True, exist_ok=True)

    summary = {"pass": 0, "fail": 0, "error": 0, "total": args.rounds}
    started = datetime.now(timezone.utc).isoformat()

    for i in range(args.rounds):
        case_no = args.start_case + i
        try:
            result = run_one(
                case_no=case_no,
                accounts=accounts,
                workbook=args.workbook,
                smash_sheet=args.smash_sheet,
                dry_run=args.dry_run,
                rules=rules,
                chance_min=args.chance_min,
                chance_max=args.chance_max,
                drain_remain=bool(args.drain_remain),
            )
            if result.get("writeFailed"):
                summary["error"] += 1
            elif result.get("verdict") == "通过":
                summary["pass"] += 1
            else:
                summary["fail"] += 1
            with progress.open("a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
                f.flush()
            if result.get("writeFailed"):
                print(
                    f"  >> 写表失败已存进度 case={case_no} verdict={result.get('verdict')} "
                    f"累计 pass={summary['pass']} fail={summary['fail']} err={summary['error']}",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                print(
                    f"  >> 已实时落表 case={case_no} verdict={result.get('verdict')} "
                    f"累计 pass={summary['pass']} fail={summary['fail']} err={summary['error']}",
                    file=sys.stderr,
                    flush=True,
                )
        except Exception as exc:  # noqa: BLE001 — 单组失败继续
            summary["error"] += 1
            err = {
                "caseNo": case_no,
                "verdict": "错误",
                "error": str(exc),
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            print(f"  ERROR case={case_no}: {exc}", file=sys.stderr)
            with progress.open("a", encoding="utf-8") as f:
                f.write(json.dumps(err, ensure_ascii=False) + "\n")
                f.flush()
            print(
                f"  >> 错误 case={case_no} 累计 err={summary['error']}",
                file=sys.stderr,
                flush=True,
            )
            # 无 smash 的异常才写错误占位行；写表失败已在进度里留有完整记录
            if not args.dry_run and "写表" not in str(exc):
                try:
                    row = record_to_row(
                        {
                            "userId": "",
                            "roomId": "",
                            "smashCount": 0,
                            "rewards": [],
                            "mysteryPrizes": [],
                        },
                        verify={
                            "caseNo": case_no,
                            "verdict": "错误",
                            "failItems": str(exc)[:200],
                        },
                    )
                    _append_with_retry(
                        lambda r=row: append_smash_record_async(
                            args.workbook, r, sheet_name=args.smash_sheet
                        )
                    )
                except Exception as write_exc:  # noqa: BLE001
                    print(f"  错误行写表失败: {write_exc}", file=sys.stderr)

    out = {
        "started": started,
        "finished": datetime.now(timezone.utc).isoformat(),
        "accounts": accounts,
        "summary": summary,
        "workbookUrl": args.workbook,
        "smashSheet": args.smash_sheet,
        "progressFile": str(progress),
        "rules": rules,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if summary["error"] == 0 and summary["fail"] == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
