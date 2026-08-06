#!/usr/bin/env python3
"""家族 PK 昨日奖励验收：匹配抓包 + 造数 PK → 计算应发 → 发奖前后钻石对比。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from moa_script_paths import moa_execute_path, moa_template, mse_execute_path, repo_root, tmp_dir

_PK_INCR = tmp_dir() / "family_pk_member_incr_2026-06-28.json"
_SHEET = (
    tmp_dir()
    / "family-pk-list/家族成员全量含手机号-20260625-165701.axls/93NwLYZXWyg4ozlzCNanyzR4JkyEqBQm_content.json"
)
_DIAMOND_TPL = moa_template("钻石-查询余额.json")
_SETTLE_TPL = moa_template("家族PK-结算发奖匹配.json")
_TUNNEL_MOMOID = "100127100"


def _run(cmd: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.check_output(cmd, cwd=cwd or repo_root(), text=True, stderr=subprocess.STDOUT)


def load_mse_config() -> dict[str, Any]:
    raw = _run(
        [
            "python3",
            str(mse_execute_path()),
            "--namespace",
            "voga-common",
            "--config-key",
            "familyPkConfig",
        ]
    )
    return json.loads(raw[raw.find("{") : raw.rfind("}") + 1])


def load_receive_rank(rank_date: str) -> dict[str, dict[str, Any]]:
    raw = _run(
        [
            "python3",
            str(moa_execute_path()),
            "--family-pk-query-receive-rank",
            "--family-pk-date",
            rank_date,
            "--family-pk-limit",
            "500",
        ]
    )
    summary = json.loads(raw[raw.find("{") :])
    return {str(x["familyId"]): x for x in summary.get("rankList", [])}


def load_member_counts() -> dict[str, int]:
    with open(_SHEET, encoding="utf-8") as f:
        data = json.load(f)
    counts: dict[str, int] = defaultdict(int)
    current_fid: str | None = None
    for row in data["content"]["kgqie6hm"]["rows"]:
        if len(row) < 3 or not isinstance(row[2], list):
            continue
        cells = {col: (cell.get("value") if isinstance(cell, dict) else cell) for col, cell in row[2]}
        fid = str(cells.get(0) or "").strip()
        if fid.isdigit():
            current_fid = fid
        uid = str(cells.get(5) or "").strip()
        if uid.isdigit() and current_fid:
            counts[current_fid] += 1
    return dict(counts)


def load_pk_scores() -> tuple[dict[tuple[str, str], int], dict[str, int], list[str]]:
    with open(_PK_INCR, encoding="utf-8") as f:
        data = json.load(f)
    member_pk: dict[tuple[str, str], int] = {}
    family_pk: dict[str, int] = {}
    users: set[str] = set()
    for item in data.get("ok", []):
        r = item.get("result") or {}
        fid = str(r.get("familyId", ""))
        uid = str(r.get("memberUserId", ""))
        if not fid or not uid:
            continue
        mps = int(r.get("memberPkScore") or 0)
        fps = int(r.get("familyPkScore") or 0)
        member_pk[(fid, uid)] = mps
        family_pk[fid] = max(family_pk.get(fid, 0), fps)
        users.add(uid)
    return member_pk, family_pk, sorted(users)


def load_tunnel_battles(pk_date: str) -> tuple[list[dict[str, Any]], list[str], str]:
    raw = _run(
        [
            "python3",
            "Tunnel/tunnel_execute.py",
            "--momoid",
            _TUNNEL_MOMOID,
            "--keyword",
            "getFamilyPkPage",
            "--since",
            "259200",
            "--output",
            "json",
        ]
    )
    d = json.loads(raw)
    lst = [
        v
        for v in (d.get("meta", {}).get("list", {}) or d.get("data", {}).get("list", {})).values()
        if "getFamilyPkPage" in v.get("url", "") and "UserList" not in v.get("url", "")
    ]
    # 昨日 tab：req date = pk_date；优先最新一条
    chosen = None
    for item in sorted(lst, key=lambda x: x.get("time", ""), reverse=True):
        req = item.get("request") or {}
        data = (item.get("response") or {}).get("data", {})
        if not isinstance(data, dict):
            continue
        if req.get("date") == pk_date and data.get("pkList"):
            chosen = item
            break
    if not chosen:
        raise RuntimeError(f"未找到 momoid={_TUNNEL_MOMOID} req_date={pk_date} 的 getFamilyPkPage 抓包")

    data = chosen["response"]["data"]
    battles: list[dict[str, Any]] = []
    bye: list[str] = []
    seen: set[str] = set()
    for p in data.get("pkList", []):
        fa = str(p["familyInfo"]["familyId"])
        opp = p.get("opponentFamily")
        fb = str(opp.get("familyId")) if opp and opp.get("familyId") else None
        if fa in seen:
            continue
        seen.add(fa)
        if fb:
            seen.add(fb)
            battles.append(
                {
                    "familyA": fa,
                    "familyB": fb,
                    "poolDiamond": int(p.get("poolDiamond") or 0),
                }
            )
        else:
            bye.append(fa)
    source = f"{chosen['time']} id={chosen['_id']} req={chosen.get('request', {}).get('date')}"
    return battles, bye, source


def bracket_for_rank(rank: int | None, brackets: list[dict[str, Any]]) -> dict[str, Any]:
    if rank is None:
        return brackets[-1]
    for b in brackets:
        rs, re = b["rankStart"], b.get("rankEnd")
        if re is None:
            if rank >= rs:
                return b
        elif rs <= rank <= re:
            return b
    return brackets[-1]


def tier_diamond(
    family_pk: int,
    receive_score: int,
    member_count: int,
    bracket: dict[str, Any],
    base_pool: int,
) -> int:
    if member_count <= 0:
        member_count = 1
    avg = receive_score / member_count
    best = base_pool
    for g in bracket.get("gradients", []):
        th = int(avg * float(g["coefficient"]))
        if family_pk >= th:
            best = int(g["bonusDiamond"])
    return best


def pool_for_battle(
    fa: str,
    fb: str | None,
    family_pk: dict[str, int],
    rank_map: dict[str, dict[str, Any]],
    fam_counts: dict[str, int],
    config: dict[str, Any],
    pool_from_api: int,
) -> int:
    base = int(config.get("basePoolDiamond", 999))
    brackets = config.get("bracketGradients", [])

    def _tier(fid: str) -> int:
        rank = rank_map.get(fid, {}).get("rank")
        recv = int(rank_map.get(fid, {}).get("receiveScore") or 0)
        br = bracket_for_rank(rank, brackets)
        return tier_diamond(family_pk.get(fid, 0), recv, fam_counts.get(fid, 1), br, base)

    if fb:
        calc = _tier(fa) + _tier(fb)
    else:
        calc = _tier(fa) * 2
    return calc


def compute_expected_rewards(
    pk_date: str,
    battles: list[dict[str, Any]],
    bye_families: list[str],
    member_pk: dict[tuple[str, str], int],
    family_pk: dict[str, int],
    rank_map: dict[str, dict[str, Any]],
    fam_counts: dict[str, int],
    config: dict[str, Any],
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    min_win = int(config.get("minWinPk", 2000))
    min_reward = int(config.get("minRewardPk", 1000))
    max_user = int(config.get("maxRewardDiamondPerUser", 100000))
    expected: dict[str, int] = defaultdict(int)
    details: list[dict[str, Any]] = []

    def _distribute(winner: str, pool: int, reason: str, opp: str | None) -> None:
        wpk = family_pk.get(winner, 0)
        detail: dict[str, Any] = {
            "winner": winner,
            "opponent": opp,
            "familyPk": wpk,
            "pool": pool,
            "reason": reason,
            "members": [],
        }
        if pool <= 0 or wpk <= 0:
            details.append(detail)
            return
        for (fid, uid), mpk in member_pk.items():
            if fid != winner:
                continue
            if mpk < min_reward:
                detail["members"].append({"userId": uid, "pk": mpk, "reward": 0, "skip": "pk<minReward"})
                continue
            reward = min((mpk * pool) // wpk, max_user)
            if reward > 0:
                expected[uid] += reward
            detail["members"].append({"userId": uid, "pk": mpk, "reward": reward})
        details.append(detail)

    for b in battles:
        fa, fb = b["familyA"], b["familyB"]
        fapk, fbpk = family_pk.get(fa, 0), family_pk.get(fb, 0)
        pool = pool_for_battle(fa, fb, family_pk, rank_map, fam_counts, config, b["poolDiamond"])
        if fapk == fbpk:
            details.append({"winner": None, "familyA": fa, "familyB": fb, "reason": "tie", "pool": pool})
            continue
        if fapk > fbpk:
            if fapk >= min_win:
                _distribute(fa, pool, "win", fb)
            else:
                details.append({"winner": None, "familyA": fa, "familyB": fb, "reason": "pk_low", "pool": pool})
        elif fbpk >= min_win:
            _distribute(fb, pool, "win", fa)
        else:
            details.append({"winner": None, "familyA": fa, "familyB": fb, "reason": "pk_low", "pool": pool})

    for fa in bye_families:
        pool = pool_for_battle(fa, None, family_pk, rank_map, fam_counts, config, 0)
        if family_pk.get(fa, 0) >= min_win:
            _distribute(fa, pool, "bye_win", None)
        else:
            details.append({"winner": None, "familyA": fa, "reason": "bye_pk_low", "pool": pool})

    return dict(expected), details


def query_diamond(uid: str) -> int:
    raw = _run(
        [
            "python3",
            str(moa_execute_path()),
            "--payload-file",
            str(_DIAMOND_TPL),
            "--diamond-query-user-id",
            uid,
            "--diamond-output",
            "summary",
        ]
    )
    summary = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
    return int(summary["diamonds"])


def batch_diamonds(user_ids: list[str], delay: float = 0.05) -> dict[str, int]:
    out: dict[str, int] = {}
    for i, uid in enumerate(user_ids):
        try:
            out[uid] = query_diamond(uid)
        except subprocess.CalledProcessError as exc:
            print(f"WARN 查钻失败 uid={uid}: {exc}", file=sys.stderr)
        if delay and i % 20 == 19:
            time.sleep(delay)
    return out


def run_settlement(settle_input_date: str) -> dict[str, Any]:
    with open(_SETTLE_TPL, encoding="utf-8") as f:
        tpl = json.load(f)
    tpl["params"][0]["value"] = settle_input_date
    tpl["params"][0]["txt"] = settle_input_date
    tpl["settings"]["time"] = "120000"
    tmp = tmp_dir() / "family_pk_settle_run.json"
    tmp.write_text(json.dumps(tpl, ensure_ascii=False), encoding="utf-8")
    raw = _run(["python3", str(moa_execute_path()), "--payload-file", str(tmp)])
    return json.loads(raw[raw.find("{") :])


def main() -> int:
    parser = argparse.ArgumentParser(description="家族 PK 昨日奖励验收")
    parser.add_argument("--pk-date", default="2026-06-28")
    parser.add_argument("--settle-date", default=None, help="runFamilyPkMatchTask 入参，默认今天")
    parser.add_argument("--skip-settle", action="store_true")
    parser.add_argument("--skip-diamond", action="store_true", help="跳过钻石查询（仅算期望）")
    args = parser.parse_args()

    pk_date = args.pk_date
    settle_date = args.settle_date or date.today().isoformat()
    rank_date = (date.fromisoformat(pk_date) - timedelta(days=1)).isoformat()
    out_path = tmp_dir() / f"family_pk_reward_verify_{pk_date}.json"

    config = load_mse_config()
    rank_map = load_receive_rank(pk_date)
    fam_counts = load_member_counts()
    member_pk, family_pk, all_users = load_pk_scores()
    battles, bye, battle_source = load_tunnel_battles(pk_date)

    expected, battle_details = compute_expected_rewards(
        pk_date, battles, bye, member_pk, family_pk, rank_map, fam_counts, config
    )
    reward_users = sorted(expected.keys())
    print(f"匹配抓包: {battle_source}")
    print(f"对战 {len(battles)} 组, 轮空 {len(bye)}, 应发奖用户 {len(reward_users)}, 应发钻合计 {sum(expected.values())}")

    result: dict[str, Any] = {
        "pkDate": pk_date,
        "settleInputDate": settle_date,
        "battleSource": battle_source,
        "battles": len(battles),
        "bye": bye,
        "expectedTotal": sum(expected.values()),
        "expectedUserCount": len(reward_users),
        "expected": expected,
        "battleDetails": battle_details,
    }

    if args.skip_diamond:
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("已写入", out_path)
        return 0

    # 只查应发奖用户 + 全量成员（用户要求所有用户）
    query_users = sorted(set(all_users))
    print(f"发奖前查钻 {len(query_users)} 人…")
    before = batch_diamonds(query_users)
    result["before"] = before

    if not args.skip_settle:
        print(f"执行 runFamilyPkMatchTask({settle_date}) …")
        settle_resp = run_settlement(settle_date)
        result["settleResponse"] = settle_resp
        inner = settle_resp.get("result", {}).get("result", settle_resp.get("result", {}))
        print("结算返回:", json.dumps(inner, ensure_ascii=False)[:500])
        time.sleep(3)

    print(f"发奖后查钻 {len(query_users)} 人…")
    after = batch_diamonds(query_users)
    result["after"] = after

    mismatches = []
    ok_count = 0
    for uid in query_users:
        exp = expected.get(uid, 0)
        b = before.get(uid)
        a = after.get(uid)
        if b is None or a is None:
            continue
        delta = a - b
        if exp == delta:
            if exp > 0:
                ok_count += 1
        elif exp > 0 or delta != 0:
            mismatches.append({"userId": uid, "expected": exp, "before": b, "after": a, "delta": delta})

    result["verify"] = {
        "matchCount": ok_count,
        "mismatchCount": len(mismatches),
        "mismatches": mismatches[:100],
        "unexpectedGain": [m for m in mismatches if m["expected"] == 0 and m["delta"] > 0][:50],
    }
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== 验收结果 ===")
    print(f"应发奖用户一致: {ok_count}/{len(reward_users)}")
    print(f"不一致: {len(mismatches)}")
    if mismatches[:5]:
        print("样例不一致:", json.dumps(mismatches[:5], ensure_ascii=False))
    print("报告:", out_path)
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
