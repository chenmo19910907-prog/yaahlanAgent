#!/usr/bin/env python3
"""CP 摩天轮档位积分返奖验收：记录/对比 60 用户钻石余额。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOP30_PATH = REPO / "adb/.state/cp_weekly_rank_top30_tunnel_100465989.json"
SNAPSHOT_PATH = REPO / "adb/.state/cp_tier_bonus_reward_snapshot.json"
MOA_PYTHON = REPO / "MOA/.venv/bin/python3"
MOA_EXECUTE = REPO / "MOA/moa_execute.py"
PAYLOAD = REPO / "MOA/templates/钻石-查询余额.json"

# MOA 档位编号 1–5 对应 D→S（数字越大档越高）
MOA_TIER_TO_LABEL: dict[int, str] = {
    1: "D",
    2: "C",
    3: "B",
    4: "A",
    5: "S",
}

# 领奖积分 → 组返奖钻石（S/A/B/C/D）
TIER_REWARDS: dict[str, list[tuple[int, int]]] = {
    "S": [
        (30_000_000, 210_000),
        (50_000_000, 350_000),
        (100_000_000, 800_000),
        (120_000_000, 960_000),
        (160_000_000, 1_280_000),
    ],
    "A": [
        (10_000_000, 60_000),
        (20_000_000, 120_000),
        (30_000_000, 210_000),
        (40_000_000, 280_000),
        (50_000_000, 400_000),
    ],
    "B": [
        (1_000_000, 5_000),
        (2_000_000, 10_000),
        (4_000_000, 24_000),
        (6_000_000, 36_000),
        (10_000_000, 70_000),
    ],
    "C": [
        (600_000, 1_800),
        (700_000, 2_800),
        (800_000, 4_000),
        (900_000, 4_500),
        (1_000_000, 6_000),
    ],
    "D": [
        (100_000, 100),
        (200_000, 200),
        (300_000, 600),
        (400_000, 800),
        (700_000, 2_800),
    ],
}

DEFAULT_MOA_TIER = 5
# 档位奖异步到账，下发后需等待再查余额（100079102 曾延迟数秒到账）
POST_DISTRIBUTE_WAIT_SEC = 8


def load_top30() -> dict:
    with TOP30_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def load_snapshot() -> dict:
    if not SNAPSHOT_PATH.exists():
        raise FileNotFoundError(f"缺少快照文件: {SNAPSHOT_PATH}，请先 init")
    with SNAPSHOT_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def save_snapshot(data: dict) -> None:
    with SNAPSHOT_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def tier_label_from_moa(moa_tier: int) -> str:
    label = MOA_TIER_TO_LABEL.get(moa_tier)
    if label is None:
        supported = ", ".join(f"{k}={v}" for k, v in sorted(MOA_TIER_TO_LABEL.items()))
        raise ValueError(f"不支持的 MOA 档位 {moa_tier}，支持: {supported}")
    return label


def claim_points_from_pair_value(pair_value: int) -> int:
    """领奖积分 = 周榜 CP 值 pairValue（与下发实测一致）。"""
    return pair_value


def group_reward_for_tier(claim_points: int, tier_label: str) -> int:
    reward = 0
    for threshold, diamonds in TIER_REWARDS[tier_label]:
        if claim_points >= threshold:
            reward = diamonds
    return reward


def expected_per_user_reward(group_reward: int) -> int:
    """CP 两人平分档位返奖钻石（与周榜一致，向下取整）。"""
    return group_reward // 2


def build_pair_row(row: dict, moa_tier: int) -> dict:
    pair_value = int(row["value"])
    claim_points = claim_points_from_pair_value(pair_value)
    tier_label = tier_label_from_moa(moa_tier)
    group_reward = group_reward_for_tier(claim_points, tier_label)
    return {
        "rank": int(row["rank"]),
        "leftUserId": str(row["leftUserId"]),
        "rightUserId": str(row["rightUserId"]),
        "moaKey": row["moaKey"],
        "pairValue": pair_value,
        "claimPoints": claim_points,
        "forcedTier": moa_tier,
        "tierLabel": tier_label,
        "groupRewardDiamonds": group_reward,
        "expectedPerUserReward": expected_per_user_reward(group_reward),
    }


def query_diamonds(user_id: str) -> int:
    python = str(MOA_PYTHON) if MOA_PYTHON.is_file() else sys.executable
    proc = subprocess.run(
        [
            python,
            str(MOA_EXECUTE),
            "--payload-file",
            str(PAYLOAD),
            "--diamond-query-user-id",
            user_id,
            "--diamond-output",
            "summary",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"查询 {user_id} 失败: {proc.stderr.strip() or proc.stdout.strip()}")
    decoder = json.JSONDecoder()
    text = proc.stdout.strip()
    idx = 0
    while idx < len(text):
        while idx < len(text) and text[idx] not in "{[":
            idx += 1
        if idx >= len(text):
            break
        try:
            payload, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            idx += 1
            continue
        if isinstance(payload, dict) and "diamonds" in payload:
            return int(payload["diamonds"])
        idx = end
    raise RuntimeError(f"查询 {user_id} 未解析到 diamonds: {proc.stdout}")


def collect_user_ids(snapshot: dict) -> list[str]:
    ids: list[str] = []
    for pair in snapshot["pairs"]:
        ids.append(str(pair["leftUserId"]))
        ids.append(str(pair["rightUserId"]))
    return ids


def tier_rule_text(moa_tier: int) -> str:
    label = tier_label_from_moa(moa_tier)
    return f"MOA batchSetCpFerrisWheelTierLevel={moa_tier} ({label}档)"


def init_snapshot(moa_tier: int) -> None:
    top30 = load_top30()
    label = tier_label_from_moa(moa_tier)
    pairs = [build_pair_row(row, moa_tier) for row in top30["top30"]]
    snapshot = {
        "rewardType": "CP摩天轮档位积分返奖",
        "moaTierMapping": "MOA 1=D, 2=C, 3=B, 4=A, 5=S",
        "tierRule": tier_rule_text(moa_tier),
        "claimPointsRule": "pairValue（周榜CP值）",
        "splitRule": "CP两人平分档位返奖钻石",
        "distributeMethod": "distributeCpFerrisWheelBonusDiamonds",
        "distributeParams": ["MENA"],
        "phase": None,
        "capturedAt": None,
        "source": top30.get("source"),
        "pairs": pairs,
        "users": {},
    }
    save_snapshot(snapshot)
    print(
        json.dumps(
            {
                "initialized": True,
                "moaTier": moa_tier,
                "tierLabel": label,
                "pairCount": len(pairs),
                "snapshot": str(SNAPSHOT_PATH),
            },
            ensure_ascii=False,
        )
    )


def recalc_snapshot(moa_tier: int | None = None) -> None:
    """保留 users 余额快照，按正确档位重算期望奖励。"""
    snapshot = load_snapshot()
    tier = moa_tier if moa_tier is not None else int(snapshot["pairs"][0].get("forcedTier", DEFAULT_MOA_TIER))
    label = tier_label_from_moa(tier)
    for pair in snapshot["pairs"]:
        updated = build_pair_row(
            {
                "rank": pair["rank"],
                "leftUserId": pair["leftUserId"],
                "rightUserId": pair["rightUserId"],
                "moaKey": pair["moaKey"],
                "value": pair["pairValue"],
            },
            tier,
        )
        pair.update(updated)
    snapshot["moaTierMapping"] = "MOA 1=D, 2=C, 3=B, 4=A, 5=S"
    snapshot["tierRule"] = tier_rule_text(tier)
    save_snapshot(snapshot)
    print(json.dumps({"recalculated": True, "moaTier": tier, "tierLabel": label}, ensure_ascii=False))


def distribute_bonus() -> None:
    """调用 distributeCpFerrisWheelBonusDiamonds(MENA)。"""
    moa_dir = REPO / "MOA"
    sys.path.insert(0, str(moa_dir))
    from moa.client import MoaClient, extract_inner_result
    from moa.env import load_local_env

    load_local_env(str(moa_dir))
    import os

    entry = os.environ.get("MOA_ENTRY_URL")
    cookie = os.environ.get("MOA_COOKIE")
    if not entry or not cookie:
        raise RuntimeError("缺少 MOA_ENTRY_URL / MOA_COOKIE")

    payload = {
        "type": "moa",
        "key": "momo.pt.toB.cosmos-server.quality-platform.codequality",
        "url": "/service/vas/external/cp-stage",
        "method": "distributeCpFerrisWheelBonusDiamonds",
        "header": "",
        "params": [
            {"title": "p1", "name": "1", "txt": "MENA", "json": "", "type": "string", "value": "MENA"},
        ],
        "settings": {"time": "60000", "group": "default", "host": "", "headerType": "TXT"},
        "region": "alpha",
        "env": "alpha",
        "cluster": "stage",
        "server": "config",
        "momoId": "df4c6f364f9fcae3",
        "momoName": "e88aa376b29864ad",
    }
    client = MoaClient(entry, cookie, 60000)
    resp = client.post(payload)
    inner_ec, inner_em, _ = extract_inner_result(resp)
    if inner_ec != 0:
        raise RuntimeError(f"档位奖下发失败: ec={inner_ec}, em={inner_em}")
    print(json.dumps({"distributed": True, "ec": inner_ec, "em": inner_em}, ensure_ascii=False))


def capture(phase: str, wait_sec: int | None = None) -> None:
    snapshot = load_snapshot()
    user_ids = collect_user_ids(snapshot)
    users = snapshot.setdefault("users", {})
    snapshot["phase"] = phase
    snapshot["capturedAt"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    if phase == "after":
        sec = POST_DISTRIBUTE_WAIT_SEC if wait_sec is None else wait_sec
        if sec > 0:
            print(f"下发后等待 {sec}s 再查询余额…", file=sys.stderr)
            time.sleep(sec)
            snapshot["postDistributeWaitSec"] = sec

    for idx, user_id in enumerate(user_ids, 1):
        entry = users.setdefault(user_id, {})
        diamonds = query_diamonds(user_id)
        if phase == "before":
            entry["diamondsBefore"] = diamonds
            entry.pop("diamondsAfter", None)
            entry.pop("actualDelta", None)
            entry.pop("match", None)
        else:
            entry["diamondsAfter"] = diamonds
            before = entry.get("diamondsBefore")
            if before is None:
                raise RuntimeError(f"用户 {user_id} 缺少 diamondsBefore，请先执行 capture --phase before")
            entry["actualDelta"] = diamonds - before
        print(f"[{idx}/{len(user_ids)}] {user_id}: {diamonds}", file=sys.stderr)

    save_snapshot(snapshot)
    print(json.dumps({"phase": phase, "userCount": len(user_ids), "snapshot": str(SNAPSHOT_PATH)}, ensure_ascii=False))


def verify() -> int:
    snapshot = load_snapshot()
    users = snapshot.get("users", {})
    expected_by_user: dict[str, int] = {}
    meta_by_user: dict[str, dict] = {}
    for pair in snapshot["pairs"]:
        expected = int(pair["expectedPerUserReward"])
        for key in ("leftUserId", "rightUserId"):
            uid = str(pair[key])
            expected_by_user[uid] = expected
            meta_by_user[uid] = pair

    rows: list[dict] = []
    mismatches = 0
    missing = 0
    for uid, expected in expected_by_user.items():
        entry = users.get(uid, {})
        before = entry.get("diamondsBefore")
        after = entry.get("diamondsAfter")
        pair = meta_by_user[uid]
        if before is None or after is None:
            missing += 1
            rows.append(
                {
                    "rank": pair["rank"],
                    "userId": uid,
                    "moaKey": pair["moaKey"],
                    "tierLabel": pair["tierLabel"],
                    "claimPoints": pair["claimPoints"],
                    "expectedDelta": expected,
                    "diamondsBefore": before,
                    "diamondsAfter": after,
                    "actualDelta": None,
                    "match": False,
                    "reason": "缺少 before/after 快照",
                }
            )
            continue
        actual = after - before
        ok = actual == expected
        if not ok and expected > 0 and actual == 0:
            reason = (
                f"期望 +{expected}，实际 +0"
                f"（可能已发过档位奖，或 capture after 前等待不足 {POST_DISTRIBUTE_WAIT_SEC}s）"
            )
        elif not ok:
            reason = f"期望 +{expected}，实际 +{actual}"
        else:
            reason = None
        if not ok:
            mismatches += 1
        rows.append(
            {
                "rank": pair["rank"],
                "userId": uid,
                "moaKey": pair["moaKey"],
                "tierLabel": pair["tierLabel"],
                "claimPoints": pair["claimPoints"],
                "groupRewardDiamonds": pair["groupRewardDiamonds"],
                "expectedDelta": expected,
                "diamondsBefore": before,
                "diamondsAfter": after,
                "actualDelta": actual,
                "match": ok,
                "reason": reason,
            }
        )

    rows.sort(key=lambda r: (r["rank"], r["userId"]))
    summary = {
        "tierRule": snapshot.get("tierRule"),
        "totalUsers": len(expected_by_user),
        "matched": sum(1 for r in rows if r["match"]),
        "mismatched": mismatches,
        "missing": missing,
        "allMatched": mismatches == 0 and missing == 0,
        "rows": rows,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["allMatched"] else 1


def print_table() -> None:
    snapshot = load_snapshot()
    users = snapshot.get("users", {})
    lines = [
        f"档位规则: {snapshot.get('tierRule', '-')}",
        "",
        "| 排名 | 档位 | 用户ID | 领奖积分 | 组返奖 | 发奖前 | 发奖后 | 实际+ | 期望+ | 一致 |",
        "|:---:|:---:|:---|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for pair in snapshot["pairs"]:
        rank = pair["rank"]
        expected = pair["expectedPerUserReward"]
        claim = pair["claimPoints"]
        group = pair["groupRewardDiamonds"]
        tier = pair["tierLabel"]
        for uid_key in ("leftUserId", "rightUserId"):
            uid = str(pair[uid_key])
            entry = users.get(uid, {})
            before = entry.get("diamondsBefore", "-")
            after = entry.get("diamondsAfter", "-")
            actual = entry.get("actualDelta", "-")
            if before != "-" and after != "-":
                match = "✅" if actual == expected else "❌"
            else:
                match = "-"
            lines.append(
                f"| {rank} | {tier} | {uid} | {claim:,} | {group:,} | {before} | {after} | {actual} | {expected} | {match} |"
            )
    print("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description="CP 档位积分返奖钻石验收")
    parser.add_argument(
        "--moa-tier",
        type=int,
        choices=sorted(MOA_TIER_TO_LABEL),
        default=DEFAULT_MOA_TIER,
        help="MOA 档位编号（1=D … 5=S，默认 5）",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="从 TOP30 tunnel 快照初始化期望奖励")
    sub.add_parser("recalc", help="按正确档位重算期望（保留余额快照）")
    sub.add_parser("distribute", help="下发档位积分返奖（distributeCpFerrisWheelBonusDiamonds）")
    cap = sub.add_parser("capture", help="采集钻石余额")
    cap.add_argument("--phase", choices=["before", "after"], required=True)
    cap.add_argument(
        "--wait",
        type=int,
        default=None,
        metavar="SEC",
        help=f"仅 after 有效：下发后等待秒数再查余额（默认 {POST_DISTRIBUTE_WAIT_SEC}；0=不等待）",
    )
    run = sub.add_parser("run", help="capture before → distribute → capture after（含等待）→ verify")
    run.add_argument(
        "--wait",
        type=int,
        default=POST_DISTRIBUTE_WAIT_SEC,
        metavar="SEC",
        help=f"下发后等待秒数再查 after 余额（默认 {POST_DISTRIBUTE_WAIT_SEC}）",
    )
    sub.add_parser("verify", help="对比 before/after 与档位期望增量")
    sub.add_parser("table", help="输出 Markdown 对比表")

    args = parser.parse_args()
    if args.cmd == "init":
        init_snapshot(args.moa_tier)
        return 0
    if args.cmd == "recalc":
        recalc_snapshot(args.moa_tier)
        return 0
    if args.cmd == "distribute":
        distribute_bonus()
        return 0
    if args.cmd == "capture":
        capture(args.phase, wait_sec=args.wait)
        return 0
    if args.cmd == "run":
        capture("before")
        distribute_bonus()
        capture("after", wait_sec=args.wait)
        return verify()
    if args.cmd == "verify":
        return verify()
    if args.cmd == "table":
        print_table()
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
