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
    apply_mystery_pending_out,
    compact_theory_tag_summary,
    compose_mystery_pending_in,
    evaluate_acceptance_verdict,
    evaluate_diamond_credit,
    expected_diamond_delta_from_smash,
    expected_vip_exp_delta_from_smash,
    format_mystery_cell,
    load_activity_rules,
    load_lottery_pools,
    lottery_id_for_egg_level,
    normalize_room_smash_lifetime,
    pending_mystery_labels,
    record_to_row,
    resolve_egg_level_at_smash,
    resolve_egg_level_label,
    theory_mystery_result,
    _reward_summary,
)
from moa.anniversary_egg_assets import (  # noqa: E402
    build_smash_asset_verify_payload,
    snapshot_user_assets,
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
    query_vip_exp,
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
    pending_in: set[str] | list[str] | None = None,
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

    expected_level = resolve_egg_level_at_smash(
        smash,
        batch=actual_smash,
        myst_room_before=myst_room_before if myst_b else None,
        egg_room_smash_before=int(smash.get("roomEggSmashBefore") or 0) if not myst_b else None,
        rules=rules,
    )
    if pending_in is not None:
        pending_before = {str(x).strip().lower() for x in pending_in if str(x).strip()}
        pending_before &= {"user", "room", "platform"}
    else:
        pending_before = set(smash.get("mysteryPendingBefore") or [])
        pending_before = {
            str(x).strip().lower()
            for x in pending_before
            if str(x).strip().lower() in {"user", "room", "platform"}
        }
    tags, pending_after = theory_mystery_result(
        user_before=user_before,
        user_after=user_after,
        room_before=myst_room_before,
        room_after=myst_room_after,
        platform_before=plat_before_i,
        platform_after=plat_after_i,
        rules=rules,
        pending_in=pending_before,
    )
    smash["mysteryPendingBefore"] = sorted(pending_before)
    smash["mysteryPendingAfter"] = sorted(pending_after)
    defer_labels = pending_mystery_labels(pending_after, rules=rules)
    theory_brief = compact_theory_tag_summary(tags)
    expected_mystery = theory_brief
    if defer_labels:
        expected_mystery = (
            f"{expected_mystery}；顺延：{'+'.join(defer_labels)}"
            if expected_mystery
            else f"顺延：{'+'.join(defer_labels)}"
        )
    actual_mystery_prizes = _reward_summary(
        smash.get("mysteryPrizes") or smash.get("mysteryRewards") or []
    )
    actual_mystery_cell = format_mystery_cell(
        actual_mystery_prizes,
        tags,
        pending_next=pending_after,
        rules=rules,
    )
    tier = _reward_summary(smash.get("rewards") or smash.get("prizes") or [])
    tier_rewards = smash.get("rewards") or smash.get("prizes") or []

    acceptance = evaluate_acceptance_verdict(
        theory_tags=tags,
        mystery_cell=actual_mystery_cell,
        tier_cell=tier,
        batch=actual_smash,
        egg_level=expected_level,
        tier_rewards=tier_rewards if isinstance(tier_rewards, list) else None,
        rules=rules,
        lottery_pools=load_lottery_pools(),
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
            "expected": (
                f"{expected_level}档次奖励非空且落在奖池 lotteryId="
                f"{lottery_id_for_egg_level(expected_level, rules=rules) or '?'} 配置内"
            ),
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
        "mysteryPendingBefore": sorted(pending_before),
        "mysteryPendingAfter": sorted(pending_after),
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
    rules: dict[str, Any] | None = None,
    pending_user: dict[str, bool] | None = None,
    pending_room: dict[str, bool] | None = None,
    pending_platform: bool = False,
) -> tuple[dict[str, int], bool]:
    """砸掉账号剩余次数（不落表），并同步跨次顺延状态。"""
    pu = pending_user if pending_user is not None else {}
    pr = pending_room if pending_room is not None else {}
    pp = pending_platform
    before = snap(user_id, room_id)["remain"]
    calls = 0
    while calls < max_calls:
        cur = snap(user_id, room_id)
        if cur["remain"] <= 0:
            break
        pending_in = compose_mystery_pending_in(
            user_id=user_id,
            room_id=room_id,
            pending_user=pu,
            pending_room=pr,
            pending_platform=pp,
        )
        smash = smash_egg_once(user_id=user_id, room_id=room_id, lang="en")
        eval_out = evaluate_case(
            smash=smash,
            rules=rules or {},
            pending_in=pending_in,
        )
        pp = apply_mystery_pending_out(
            user_id=user_id,
            room_id=room_id,
            pending_out=eval_out.get("mysteryPendingAfter") or [],
            pending_user=pu,
            pending_room=pr,
        )
        calls += 1
        time.sleep(0.15)
    after = snap(user_id, room_id)["remain"]
    return (
        {"remainBefore": before, "remainAfter": after, "drainCalls": calls},
        pp,
    )


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
    pending_user: dict[str, bool] | None = None,
    pending_room: dict[str, bool] | None = None,
    pending_platform: bool = False,
) -> dict[str, Any]:
    actor = random.choice(accounts)
    smash_room = random.choice(accounts)["roomId"]
    lo = min(int(chance_min), int(chance_max))
    hi = max(int(chance_min), int(chance_max))
    target = random.randint(lo, hi)
    phone = actor["phone"]
    user_id = actor["userId"]
    gift_room = actor["roomId"]
    pu = pending_user if pending_user is not None else {}
    pr = pending_room if pending_room is not None else {}
    pp = pending_platform

    print(
        f"[{case_no}] phone={phone} user={user_id} giftRoom={gift_room} "
        f"smashRoom={smash_room} targetChances={target}",
        file=sys.stderr,
    )

    drain_info: dict[str, int] | None = None
    if drain_remain:
        drain_info, pp = drain_remain_chances(
            user_id,
            gift_room,
            rules=rules,
            pending_user=pu,
            pending_room=pr,
            pending_platform=pp,
        )
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

    pending_in = compose_mystery_pending_in(
        user_id=user_id,
        room_id=smash_room,
        pending_user=pu,
        pending_room=pr,
        pending_platform=pp,
    )
    if pending_in:
        print(f"  pending_in={sorted(pending_in)}", file=sys.stderr)

    diamond_before = query_diamond_balance(user_id)
    vip_before = query_vip_exp(user_id)
    assets_before = snapshot_user_assets(user_id, smash_room)
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

    asset_verify = build_smash_asset_verify_payload(
        user_id=user_id,
        room_id=smash_room,
        smash=smash,
        diamond_before=diamond_before,
        vip_before=vip_before,
        assets_before=assets_before,
    )
    asset_payload = asset_verify["payload"]
    diamond_check = asset_verify["diamond"]
    vip_check = asset_verify["vipExp"]
    backpack_check = asset_verify["backpack"]
    prop_check = asset_verify["prop"]
    voucher_check = asset_verify["voucher"]
    print(
        f"  diamond expected={asset_payload.get('expectedDiamond')} "
        f"{asset_payload.get('diamondBefore')}→{asset_payload.get('diamondAfter')} "
        f"delta={diamond_check.get('actualDelta')} | "
        f"vip expected={asset_payload.get('expectedVipExp')} "
        f"{asset_payload.get('vipExpBefore')}→{asset_payload.get('vipExpAfter')} "
        f"delta={vip_check.get('actualDelta')} | "
        f"backpack expected={asset_payload.get('expectedBackpack')} "
        f"delta={backpack_check.get('actualDelta')} | "
        f"prop expected={asset_payload.get('expectedProp')} "
        f"delta={prop_check.get('actualDelta')} | "
        f"voucher expected={asset_payload.get('expectedVoucher')} "
        f"delta={voucher_check.get('actualDelta')}",
        file=sys.stderr,
    )

    eval_out = evaluate_case(smash=smash, rules=rules, pending_in=pending_in)
    pp = apply_mystery_pending_out(
        user_id=user_id,
        room_id=smash_room,
        pending_out=eval_out.get("mysteryPendingAfter") or [],
        pending_user=pu,
        pending_room=pr,
    )
    if eval_out.get("mysteryPendingAfter"):
        print(
            f"  pending_out={eval_out.get('mysteryPendingAfter')}",
            file=sys.stderr,
        )
    verify_payload = {
        "caseNo": case_no,
        "phone": phone,
        "userId": user_id,
        "roomId": smash_room,
        "targetChances": target,
        "gainedChances": gift_info["gainedChances"],
        "topUpDiamonds": gift_info["topUpDiamonds"],
        **asset_payload,
        **eval_out,
    }
    row_smash = record_to_row(
        smash,
        fallback_user_id=user_id,
        fallback_room_id=smash_room,
        fallback_smash_count=smash.get("smashCount"),
        verify=verify_payload,
    )
    combined_verdict = str(row_smash[-2] or "").strip()

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
        "diamond": diamond_check,
        "vipExp": vip_check,
        "backpack": backpack_check,
        "prop": prop_check,
        "voucher": voucher_check,
        "assetsBefore": assets_before,
        "verdict": combined_verdict,
        "pendingPlatform": pp,
    }

    if dry_run:
        print(f"  dry-run verdict={combined_verdict}", file=sys.stderr)
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


def _build_batch_result_markdown(
    *,
    phones: list[str],
    accounts: list[dict[str, str]],
    summary: dict[str, int],
    workbook: str,
    chance_min: int,
    chance_max: int,
    fail_details: list[str],
) -> str:
    total = int(summary.get("total") or 0)
    passed = int(summary.get("pass") or 0)
    failed = int(summary.get("fail") or 0)
    errors = int(summary.get("error") or 0)
    pass_rate = f"{passed * 100 / total:.1f}%" if total else "0%"
    acct_lines = [
        f"- **{a['phone']}**（userId `{a['userId']}`，房间 `{a['roomId']}`）"
        for a in accounts
    ]
    chance_desc = (
        f"**{chance_min}**"
        if chance_min == chance_max
        else f"**{chance_min}~{chance_max}**"
    )
    lines = [
        "## 砸金蛋批量验收结果",
        "",
        f"- 测试账号：{', '.join(phones)}",
        *acct_lines,
        f"- 测试组数：**{total}**（每组自送获次 {chance_desc} 次 → 两账号房间随机砸蛋）",
        f"- 验收通过：**{passed}**，失败：**{failed}**，错误：**{errors}**，通过率 **{pass_rate}**",
        f"- 记录表：[砸金蛋测试记录]({workbook})",
        "",
        "### 验收说明",
        "",
        "对照 MSE 配置验收：神秘奖励保底、金蛋等级礼物非空、砸蛋次数与累加计数、钻石到账。",
    ]
    if fail_details:
        lines.extend(["", "### 未通过/异常明细（节选）", ""])
        for item in fail_details[:25]:
            lines.append(f"- {item}")
        if len(fail_details) > 25:
            lines.append(f"- …另有 {len(fail_details) - 25} 条")
    return "\n".join(lines)


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
    parser.add_argument("--user-key", default="", help="钉钉 batch_key，用于批量进度上报")
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
    pending_user: dict[str, bool] = {}
    pending_room: dict[str, bool] = {}
    pending_platform = False
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
            "砸蛋验收",
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
                accounts=accounts,
                workbook=args.workbook,
                smash_sheet=args.smash_sheet,
                dry_run=args.dry_run,
                rules=rules,
                chance_min=args.chance_min,
                chance_max=args.chance_max,
                drain_remain=bool(args.drain_remain),
                pending_user=pending_user,
                pending_room=pending_room,
                pending_platform=pending_platform,
            )
            pending_platform = bool(result.get("pendingPlatform"))
            if result.get("writeFailed"):
                summary["error"] += 1
                fail_details.append(
                    f"第{case_no}组：写表失败（{result.get('writeError', '')[:80]}）"
                )
            elif result.get("verdict") == "通过":
                summary["pass"] += 1
            else:
                summary["fail"] += 1
                fail_details.append(
                    f"第{case_no}组：{result.get('verdict')} "
                    f"({'; '.join(result.get('eval', {}).get('failItems') or [])})"
                )
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
            _report_progress(i + 1)
        except Exception as exc:  # noqa: BLE001 — 单组失败继续
            summary["error"] += 1
            fail_details.append(f"第{case_no}组：错误（{str(exc)[:120]}）")
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
            _report_progress(i + 1)
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

    if args.user_key and args.rounds >= 3:
        _report_progress(
            args.rounds,
            result_text=_build_batch_result_markdown(
                phones=phones,
                accounts=accounts,
                summary=summary,
                workbook=args.workbook,
                chance_min=args.chance_min,
                chance_max=args.chance_max,
                fail_details=fail_details,
            ),
        )

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
