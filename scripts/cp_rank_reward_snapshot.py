#!/usr/bin/env python3
"""CP 周榜奖励验收：记录/对比 60 用户钻石余额。"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = REPO / "adb/.state/cp_weekly_rank_reward_snapshot.json"
MOA_EXECUTE = REPO / "MOA/moa_execute.py"
PAYLOAD = REPO / "MOA/templates/钻石-查询余额.json"


def load_snapshot() -> dict:
    with SNAPSHOT_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def save_snapshot(data: dict) -> None:
    with SNAPSHOT_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def query_diamonds(user_id: str) -> int:
    proc = subprocess.run(
        [
            sys.executable,
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
    text = proc.stdout.strip()
    decoder = json.JSONDecoder()
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


def capture(phase: str) -> None:
    snapshot = load_snapshot()
    user_ids = collect_user_ids(snapshot)
    users = snapshot.setdefault("users", {})
    snapshot["phase"] = phase
    snapshot["capturedAt"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

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
    rank_by_user: dict[str, int] = {}
    for pair in snapshot["pairs"]:
        expected = int(pair["expectedPerUserReward"])
        rank = int(pair["rank"])
        for key in ("leftUserId", "rightUserId"):
            uid = str(pair[key])
            expected_by_user[uid] = expected
            rank_by_user[uid] = rank

    rows: list[dict] = []
    mismatches = 0
    missing = 0
    for uid, expected in expected_by_user.items():
        entry = users.get(uid, {})
        before = entry.get("diamondsBefore")
        after = entry.get("diamondsAfter")
        if before is None or after is None:
            missing += 1
            rows.append(
                {
                    "rank": rank_by_user[uid],
                    "userId": uid,
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
        if not ok:
            mismatches += 1
        rows.append(
            {
                "rank": rank_by_user[uid],
                "userId": uid,
                "expectedDelta": expected,
                "diamondsBefore": before,
                "diamondsAfter": after,
                "actualDelta": actual,
                "match": ok,
                "reason": None if ok else f"期望 +{expected}，实际 +{actual}",
            }
        )

    rows.sort(key=lambda r: (r["rank"], r["userId"]))
    summary = {
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
    lines = ["| 排名 | 用户ID | 发奖前钻石 | 发奖后钻石 | 实际增量 | 期望增量 | 一致 |", "|:---:|:---|---:|---:|---:|---:|:---:|"]
    for pair in snapshot["pairs"]:
        rank = pair["rank"]
        expected = pair["expectedPerUserReward"]
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
            lines.append(f"| {rank} | {uid} | {before} | {after} | {actual} | {expected} | {match} |")
    print("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description="CP 周榜奖励钻石验收快照")
    sub = parser.add_subparsers(dest="cmd", required=True)

    cap = sub.add_parser("capture", help="采集钻石余额")
    cap.add_argument("--phase", choices=["before", "after"], required=True)

    sub.add_parser("verify", help="对比 before/after 与期望增量")
    sub.add_parser("table", help="输出 Markdown 对比表")

    args = parser.parse_args()
    if args.cmd == "capture":
        capture(args.phase)
        return 0
    if args.cmd == "verify":
        return verify()
    if args.cmd == "table":
        print_table()
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
