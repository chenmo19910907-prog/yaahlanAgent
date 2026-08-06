#!/usr/bin/env python3
"""查询 3 周年砸金蛋神秘保底计数（用户/房间/平台），并判断是否应触发神秘奖。"""

from __future__ import annotations

import argparse
import json
import sys

from moa_script_paths import ensure_gateway_path, ensure_moa_gift_paths

GATEWAY_DIR = ensure_gateway_path()
ensure_moa_gift_paths()

from anniversary_egg_smash_to_workbook import load_activity_rules  # noqa: E402
from moa.anniversary_egg import (  # noqa: E402
    get_mystery_count,
    mystery_guarantee_expected,
    resolve_own_room_id,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="year3Dao.testGetMysteryCount → 用户/房间/平台砸蛋次数 + 神秘保底判定"
    )
    parser.add_argument("--user-id", required=True, help="用户 ID")
    parser.add_argument(
        "--room-id",
        default="",
        help="房间 ID（默认 Admin 查自己的房间）",
    )
    parser.add_argument(
        "--type",
        default="2",
        dest="type_flag",
        help='testGetMysteryCount 第一参，默认 "2"（累加验收）；质量平台对照用 "1"',
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=0,
        help="假设再砸 N 次，预判是否越过保底（0=只查当前）",
    )
    args = parser.parse_args()

    user_id = str(args.user_id).strip()
    room_id = str(args.room_id or "").strip()
    if not room_id:
        room_id = resolve_own_room_id(user_id)

    counts = get_mystery_count(user_id, room_id, type_flag=args.type_flag)
    rules = load_activity_rules(force_refresh=True)
    u_mod = int(rules.get("user_guarantee_mod") or 50)
    r_mod = int(rules.get("room_guarantee_mod") or 100)
    p_mod = int(rules.get("platform_guarantee_mod") or 150)

    batch = max(0, int(args.batch or 0))
    user_b, room_b, plat_b = counts["user"], counts["room"], counts["platform"]
    assume = batch if batch > 0 else 1
    tags, pending_next = mystery_guarantee_expected(
        user_before=user_b,
        user_after=user_b + assume,
        room_before=room_b,
        room_after=room_b + assume,
        platform_before=plat_b,
        platform_after=plat_b + assume,
        user_mod=u_mod,
        room_mod=r_mod,
        platform_mod=p_mod,
    )

    def _next_mod(cur: int, mod: int) -> int | None:
        if mod <= 0:
            return None
        return (cur // mod + 1) * mod

    out = {
        "ok": True,
        "userId": user_id,
        "roomId": room_id,
        "type": args.type_flag,
        "counts": {
            "user": user_b,
            "room": room_b,
            "platform": plat_b,
        },
        "guaranteeMods": {
            "user": u_mod,
            "room": r_mod,
            "platform": p_mod,
            "source": rules.get("source"),
        },
        "nextGuaranteeAt": {
            "user": _next_mod(user_b, u_mod),
            "room": _next_mod(room_b, r_mod),
            "platform": _next_mod(plat_b, p_mod),
        },
        "batchAssume": assume,
        "expectedMysteryIfSmashBatch": tags,
        "mysteryPendingNext": sorted(pending_next),
        "mysteryShouldIssue": bool(tags),
        "note": (
            "counts 来自 year3Dao.testGetMysteryCount(type,userId,roomId)；"
            "默认按再砸 1 次预判是否越过用户/房间/平台保底模数；"
            "--batch N 可改为预判再砸 N 次；"
            "同帧多保底未消耗项写入 mysteryPendingNext，应作为下一次砸蛋预期起点"
        ),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2) from exc
