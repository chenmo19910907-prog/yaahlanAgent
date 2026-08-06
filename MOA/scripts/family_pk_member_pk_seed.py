#!/usr/bin/env python3
"""清除指定日期 PK → 全员随机 PK → 按匹配结果纠偏三类场景 → 写入造数报告。"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import subprocess
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any

from moa_script_paths import gateway_dir, moa_execute_path, moa_template, repo_root, tmp_dir

_GATEWAY = gateway_dir()
if str(_GATEWAY) not in sys.path:
    sys.path.insert(0, str(_GATEWAY))

from family_pk_calc_utils import (  # noqa: E402
    load_family_pk_config_from_workbook,
    parse_battles_from_match_verify_sheet,
)
from mse_workbook_utils import fetch_workbook_sheets_async, node_id  # noqa: E402

DEFAULT_WORKBOOK = "https://alidocs.dingtalk.com/i/nodes/N7dx2rn0JbZQqA9ACZ1MoaaRJMGjLRb3"
DEFAULT_SHEET = "家族列表"
DEFAULT_MATCH_SHEET = "匹配验收"
_CLEAR_PK_TPL = moa_template("家族PK-删除全部PK值.json")
_ALL_SCENARIOS = ["win", "tie", "pk_low", "member_low", "bye_win", "bye_pk_low", "random"]


def _cell(row: list[Any], idx: int) -> str:
    if idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


async def load_members_from_workbook(
    workbook_url_or_id: str,
    *,
    sheet_name: str = DEFAULT_SHEET,
) -> list[dict[str, str]]:
    workbook_id = node_id(workbook_url_or_id)
    url = f"https://alidocs.dingtalk.com/i/nodes/{workbook_id}"
    sheets = await fetch_workbook_sheets_async(url)
    if sheet_name not in sheets:
        raise RuntimeError(f"未找到工作表: {sheet_name}")
    members: list[dict[str, str]] = []
    current_fid = ""
    current_name = ""
    for row in sheets[sheet_name]:
        fid = _cell(row, 0)
        if fid.isdigit():
            current_fid = fid
            current_name = _cell(row, 1)
        uid = _cell(row, 2)
        if uid.isdigit() and current_fid:
            members.append(
                {
                    "familyId": current_fid,
                    "familyName": current_name,
                    "memberUserId": uid,
                    "isLeader": _cell(row, 4),
                }
            )
    if not members:
        raise RuntimeError(f"工作表 {sheet_name} 未解析到成员")
    return members


def load_members_sync(workbook: str, *, sheet_name: str) -> list[dict[str, str]]:
    return asyncio.run(load_members_from_workbook(workbook, sheet_name=sheet_name))


async def load_battles_from_workbook(
    workbook_url_or_id: str,
    *,
    sheet_name: str = DEFAULT_MATCH_SHEET,
) -> tuple[list[dict[str, Any]], list[str]]:
    """从钉钉「匹配验收」读取对战/轮空，不依赖抓包。"""
    workbook_id = node_id(workbook_url_or_id)
    url = f"https://alidocs.dingtalk.com/i/nodes/{workbook_id}"
    sheets = await fetch_workbook_sheets_async(url)
    if sheet_name not in sheets:
        raise RuntimeError(f"未找到工作表: {sheet_name}，请先执行匹配验收步骤")
    return parse_battles_from_match_verify_sheet(sheets[sheet_name])


def load_battles_sync(workbook: str, *, sheet_name: str) -> tuple[list[dict[str, Any]], list[str]]:
    return asyncio.run(load_battles_from_workbook(workbook, sheet_name=sheet_name))


def _clear_pk(pk_date: str, area: str = "MENA") -> dict[str, Any]:
    tpl = json.loads(_CLEAR_PK_TPL.read_text(encoding="utf-8"))
    body = {"date": pk_date, "area": area}
    tpl["params"][0]["value"] = body
    tpl["params"][0]["json"] = json.dumps(body, ensure_ascii=False)
    payload = tmp_dir() / f"family_pk_clear_pk_{pk_date}.json"
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_text(json.dumps(tpl, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(moa_execute_path()), "--payload-file", str(payload)],
        cwd=str(repo_root()),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "清除 PK 失败")[-500:])
    text = proc.stdout
    return json.loads(text[text.find("{") : text.rfind("}") + 1])


def _incr_pk(pk_date: str, family_id: str, member_user_id: str, pk_delta: int) -> dict[str, Any]:
    body = {
        "lang": "zh",
        "date": pk_date,
        "familyId": family_id,
        "memberUserId": member_user_id,
        "pkDelta": pk_delta,
        "updateBattleRank": True,
    }
    tpl = {
        "type": "moa",
        "key": "momo.pt.toB.cosmos-server.quality-platform.codequality",
        "url": "/service/vas/internal/family-pk-moa",
        "method": "incrFamilyPkScoreForTest",
        "header": "",
        "params": [{"name": 0, "title": "", "txt": "", "json": json.dumps(body, ensure_ascii=False), "type": "json", "value": body}],
        "settings": {"time": 2000, "group": "default", "host": "", "headerType": "TXT"},
        "region": "alpha",
        "env": "alpha",
        "cluster": "stage",
        "server": "config",
        "momoId": "df4c6f364f9fcae3",
        "momoName": "e88aa376b29864ad",
    }
    payload = tmp_dir() / f"incr_pk_{family_id}_{member_user_id}_{pk_date}.json"
    payload.write_text(json.dumps(tpl, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(moa_execute_path()), "--payload-file", str(payload)],
        cwd=str(repo_root()),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "增加 PK 失败")[-500:])
    resp = json.loads(proc.stdout[proc.stdout.find("{") :])
    inner_wrap = resp.get("result", {}).get("result", {})
    inner = inner_wrap.get("data") if isinstance(inner_wrap, dict) else None
    if inner is None and isinstance(inner_wrap, dict):
        inner = inner_wrap
    if not isinstance(inner, dict):
        return {"ok": False, "response": inner_wrap}
    return {"ok": True, "result": inner}


def _family_total(member_pk: dict[tuple[str, str], int], fid: str, members: list[dict[str, str]]) -> int:
    return sum(member_pk.get((fid, m["memberUserId"]), 0) for m in members)


def _battle_winner(
    fa: str,
    fb: str,
    member_pk: dict[tuple[str, str], int],
    by_family: dict[str, list[dict[str, str]]],
) -> tuple[str, str, int, int] | None:
    fapk = _family_total(member_pk, fa, by_family[fa])
    fbpk = _family_total(member_pk, fb, by_family[fb])
    if fapk == fbpk:
        return None
    if fapk > fbpk:
        return fa, fb, fapk, fbpk
    return fb, fa, fbpk, fapk


def _reduce_member_pk(
    member_pk: dict[tuple[str, str], int],
    fid: str,
    uid: str,
    amount: int,
) -> int:
    """从成员扣减 PK（amount>0），返回实际扣减量。"""
    if amount <= 0:
        return 0
    key = (fid, uid)
    have = member_pk.get(key, 0)
    take = min(have, amount)
    member_pk[key] = have - take
    return take


def _reduce_family_total(
    member_pk: dict[tuple[str, str], int],
    fid: str,
    members: list[dict[str, str]],
    amount: int,
) -> int:
    """从家族各成员按 PK 从高到低扣减，返回实际扣减量。"""
    if amount <= 0:
        return 0
    reduced = 0
    ranked = sorted(members, key=lambda m: member_pk.get((fid, m["memberUserId"]), 0), reverse=True)
    for member in ranked:
        if reduced >= amount:
            break
        uid = member["memberUserId"]
        reduced += _reduce_member_pk(member_pk, fid, uid, amount - reduced)
    return reduced


def _set_family_total(
    member_pk: dict[tuple[str, str], int],
    fid: str,
    members: list[dict[str, str]],
    target: int,
) -> None:
    current = _family_total(member_pk, fid, members)
    if current <= target:
        return
    _reduce_family_total(member_pk, fid, members, current - target)


def _apply_tie_case(
    battle: dict[str, Any],
    member_pk: dict[tuple[str, str], int],
    by_family: dict[str, list[dict[str, str]]],
) -> dict[str, Any] | None:
    fa, fb = battle["familyA"], battle["familyB"]
    outcome = _battle_winner(fa, fb, member_pk, by_family)
    if not outcome:
        return None
    winner, loser, winner_pk, loser_pk = outcome
    diff = winner_pk - loser_pk
    reduced = _reduce_family_total(member_pk, winner, by_family[winner], diff)
    if reduced < diff:
        return None
    return {
        "type": "tie",
        "familyA": fa,
        "familyB": fb,
        "adjustedFamily": winner,
        "reducedPk": reduced,
        "note": f"胜方{winner}扣减{reduced}PK与{loser}持平",
    }


def _apply_member_low_case(
    battle: dict[str, Any],
    member_pk: dict[tuple[str, str], int],
    by_family: dict[str, list[dict[str, str]]],
    *,
    min_reward: int,
    rng: random.Random,
) -> dict[str, Any] | None:
    fa, fb = battle["familyA"], battle["familyB"]
    outcome = _battle_winner(fa, fb, member_pk, by_family)
    if not outcome:
        return None
    winner, loser, winner_pk, loser_pk = outcome
    members = by_family[winner]
    if not members:
        return None
    target = max(1, min_reward - rng.randint(1, max(1, min(200, min_reward // 2))))
    if min_reward > 100:
        target = rng.randint(max(1, min_reward // 4), min_reward - 1)
    pick = max(members, key=lambda m: member_pk.get((winner, m["memberUserId"]), 0))
    uid = pick["memberUserId"]
    current = member_pk.get((winner, uid), 0)
    if current <= target:
        if current >= min_reward:
            target = max(1, min_reward - rng.randint(1, max(1, min(200, min_reward // 2))))
        else:
            return {
                "type": "member_low",
                "familyA": fa,
                "familyB": fb,
                "winner": winner,
                "memberUserId": uid,
                "targetPk": current,
                "note": f"胜方成员{uid}已低于参数表领奖最低PK({min_reward})",
            }
    reduced = _reduce_member_pk(member_pk, winner, uid, current - target)
    return {
        "type": "member_low",
        "familyA": fa,
        "familyB": fb,
        "winner": winner,
        "memberUserId": uid,
        "targetPk": member_pk.get((winner, uid), 0),
        "reducedPk": reduced,
        "note": f"胜方成员{uid}降至{member_pk.get((winner, uid), 0)}(<参数表minRewardPk={min_reward})",
    }


def _apply_pk_low_case(
    battle: dict[str, Any],
    member_pk: dict[tuple[str, str], int],
    by_family: dict[str, list[dict[str, str]]],
    *,
    min_win: int,
    rng: random.Random,
) -> dict[str, Any]:
    fa, fb = battle["familyA"], battle["familyB"]
    targets: dict[str, int] = {}
    for fid in (fa, fb):
        members = by_family.get(fid, [])
        if not members:
            continue
        current = _family_total(member_pk, fid, members)
        if current >= min_win:
            cap = min_win - 1
            floor = max(1, min_win // 4)
            targets[fid] = rng.randint(floor, max(floor, cap))
        else:
            targets[fid] = current
    for fid, target in targets.items():
        _set_family_total(member_pk, fid, by_family[fid], target)
    return {
        "type": "pk_low",
        "familyA": fa,
        "familyB": fb,
        "familyPkA": _family_total(member_pk, fa, by_family[fa]),
        "familyPkB": _family_total(member_pk, fb, by_family[fb]),
        "note": f"双方家族PK均<参数表minWinPk({min_win})",
    }


def _member_count(fid: str, by_family: dict[str, list[dict[str, str]]]) -> int:
    return len(by_family.get(fid, []))


def _both_small_families(
    battle: dict[str, Any],
    by_family: dict[str, list[dict[str, str]]],
    *,
    max_members: int = 9,
) -> bool:
    """个位数成员家族：成员数 1~max_members（默认 ≤9）。"""
    return (
        0 < _member_count(battle["familyA"], by_family) <= max_members
        and 0 < _member_count(battle["familyB"], by_family) <= max_members
    )


def _battle_size_rank(
    battle: dict[str, Any],
    by_family: dict[str, list[dict[str, str]]],
    *,
    max_members: int = 9,
) -> tuple[int, int, int]:
    """排序键：优先双方均为小族，其次最大成员数更小、合计更小。"""
    fa, fb = battle["familyA"], battle["familyB"]
    ca, cb = _member_count(fa, by_family), _member_count(fb, by_family)
    both_small = int(_both_small_families(battle, by_family, max_members=max_members))
    return (-both_small, max(ca, cb), ca + cb)


def _pick_battle_for_case(
    battles: list[dict[str, Any]],
    *,
    by_family: dict[str, list[dict[str, str]]],
    member_pk: dict[tuple[str, str], int],
    used_keys: set[tuple[str, str]],
    rng: random.Random,
    require_winner: bool = False,
    max_members: int = 9,
) -> dict[str, Any] | None:
    """特殊场景优先选用双方均为个位数成员的小家族对战，避免大家族被强行拉成平局。"""
    pool = [b for b in battles if _battle_key(b) not in used_keys]
    if require_winner:
        pool = [
            b
            for b in pool
            if _battle_winner(b["familyA"], b["familyB"], member_pk, by_family) is not None
        ]
    if not pool:
        return None

    small = [b for b in pool if _both_small_families(b, by_family, max_members=max_members)]
    if small:
        pool = small
    else:
        pool = sorted(pool, key=lambda b: _battle_size_rank(b, by_family, max_members=max_members))
        best = _battle_size_rank(pool[0], by_family, max_members=max_members)
        pool = [b for b in pool if _battle_size_rank(b, by_family, max_members=max_members) == best]

    rng.shuffle(pool)
    return pool[0]


def _battle_key(battle: dict[str, Any]) -> tuple[str, str]:
    fa, fb = battle["familyA"], battle["familyB"]
    return tuple(sorted((fa, fb)))  # type: ignore[return-value]


def build_pk_plan(
    *,
    members: list[dict[str, str]],
    battles: list[dict[str, Any]],
    bye_families: list[str],
    config: dict[str, Any],
    max_score: int,
    seed: int | None,
) -> tuple[list[dict[str, Any]], dict[str, int], dict[tuple[str, str], int], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    1. 全员随机 PK（0~max_score）
    2. 对战来自「匹配验收」最新列表
    3. 纠偏：平局 + 双方低于 minWinPk（优先个位数成员小家族）
    """
    rng = random.Random(seed)
    min_win = int(config["minWinPk"])
    min_reward = int(config["minRewardPk"])

    by_family: dict[str, list[dict[str, str]]] = defaultdict(list)
    for m in members:
        by_family[m["familyId"]].append(m)

    member_pk: dict[tuple[str, str], int] = {}
    for m in members:
        fid, uid = m["familyId"], m["memberUserId"]
        member_pk[(fid, uid)] = rng.randint(0, max_score)

    special_cases: list[dict[str, Any]] = []
    used_keys: set[tuple[str, str]] = set()

    tie_battle = _pick_battle_for_case(
        battles,
        by_family=by_family,
        member_pk=member_pk,
        used_keys=used_keys,
        rng=rng,
        require_winner=True,
    )
    if tie_battle:
        case = _apply_tie_case(tie_battle, member_pk, by_family)
        if case:
            case["familyAMembers"] = _member_count(tie_battle["familyA"], by_family)
            case["familyBMembers"] = _member_count(tie_battle["familyB"], by_family)
            special_cases.append(case)
            used_keys.add(_battle_key(tie_battle))

    pk_low_battle = _pick_battle_for_case(
        battles,
        by_family=by_family,
        member_pk=member_pk,
        used_keys=used_keys,
        rng=rng,
        require_winner=False,
    )
    if pk_low_battle:
        case = _apply_pk_low_case(
            pk_low_battle, member_pk, by_family, min_win=min_win, rng=rng
        )
        case["familyAMembers"] = _member_count(pk_low_battle["familyA"], by_family)
        case["familyBMembers"] = _member_count(pk_low_battle["familyB"], by_family)
        special_cases.append(case)
        used_keys.add(_battle_key(pk_low_battle))

    case_by_key: dict[tuple[str, str], str] = {}
    for case in special_cases:
        key = _battle_key({"familyA": case["familyA"], "familyB": case["familyB"]})
        case_by_key[key] = case["type"]

    family_totals: dict[str, int] = {
        fid: _family_total(member_pk, fid, fam_members)
        for fid, fam_members in by_family.items()
    }

    battle_plans: list[dict[str, Any]] = []
    for battle in battles:
        fa, fb = battle["familyA"], battle["familyB"]
        scenario = case_by_key.get(_battle_key(battle), "win")
        fapk = family_totals.get(fa, 0)
        fbpk = family_totals.get(fb, 0)
        battle_plans.append(
            {
                "familyA": fa,
                "familyB": fb,
                "scenario": scenario,
                "familyPkA": fapk,
                "familyPkB": fbpk,
            }
        )

    for fid in bye_families:
        if fid not in family_totals:
            continue
        fapk = family_totals[fid]
        scenario = "bye_win" if fapk >= min_win else "bye_pk_low"
        battle_plans.append(
            {
                "familyA": fid,
                "familyB": None,
                "scenario": scenario,
                "familyPkA": fapk,
                "familyPkB": 0,
            }
        )

    battle_scenario_for_family: dict[str, str] = {}
    for plan in battle_plans:
        scenario = plan.get("scenario", "win")
        for fid in (plan.get("familyA"), plan.get("familyB")):
            if fid:
                battle_scenario_for_family[str(fid)] = scenario

    assignments: list[dict[str, Any]] = []
    for m in members:
        fid, uid = m["familyId"], m["memberUserId"]
        pk = member_pk.get((fid, uid), 0)
        assignments.append(
            {
                **m,
                "pkDelta": pk,
                "scenario": battle_scenario_for_family.get(fid, "random"),
            }
        )

    return battle_plans, family_totals, member_pk, assignments, special_cases


def run_member_pk_seed(
    *,
    workbook: str,
    pk_date: str,
    max_score: int,
    sheet_name: str,
    match_sheet: str,
    seed: int | None,
    dry_run: bool,
    skip_clear: bool,
) -> dict[str, Any]:
    members = load_members_sync(workbook, sheet_name=sheet_name)
    config = load_family_pk_config_from_workbook(workbook)
    rank_date = (datetime_from_iso(pk_date) - timedelta(days=1)).isoformat()
    battles, bye = load_battles_sync(workbook, sheet_name=match_sheet)

    battle_plans, family_totals, member_pk, assignments, special_cases = build_pk_plan(
        members=members,
        battles=battles,
        bye_families=bye,
        config=config,
        max_score=max_score,
        seed=seed,
    )

    summary: dict[str, Any] = {
        "pkDate": pk_date,
        "rankDate": rank_date,
        "maxScore": max_score,
        "seed": seed,
        "minWinPk": int(config["minWinPk"]),
        "minRewardPk": int(config["minRewardPk"]),
        "memberCount": len(assignments),
        "familyCount": len({a["familyId"] for a in assignments}),
        "battleCount": len(battles),
        "byeCount": len(bye),
        "battlePlans": battle_plans,
        "matchSheet": match_sheet,
        "specialCases": special_cases,
        "scenarios": {s: sum(1 for b in battle_plans if b.get("scenario") == s) for s in _ALL_SCENARIOS},
        "assignments": assignments,
        "ok": [],
        "failed": [],
    }

    out_path = tmp_dir() / f"family_pk_member_pk_seed_{pk_date}.json"
    if dry_run:
        summary["dryRun"] = True
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        summary["reportPath"] = str(out_path)
        return summary

    if not skip_clear:
        summary["clearPkResponse"] = _clear_pk(pk_date)

    ok = fail = 0
    for item in assignments:
        fid = item["familyId"]
        uid = item["memberUserId"]
        delta = int(item["pkDelta"])
        rec = dict(item)
        if delta == 0:
            rec["status"] = "skip"
            rec["note"] = "PK增量为0"
            summary["ok"].append(rec)
            ok += 1
            continue
        try:
            result = _incr_pk(pk_date, fid, uid, delta)
            if result["ok"]:
                ok += 1
                rec["status"] = "ok"
                rec["result"] = result["result"]
                summary["ok"].append(rec)
            else:
                fail += 1
                rec["status"] = "fail"
                rec["response"] = result.get("response")
                summary["failed"].append(rec)
        except RuntimeError as exc:
            fail += 1
            rec["status"] = "error"
            rec["error"] = str(exc)
            summary["failed"].append(rec)

    summary["success"] = ok
    summary["failedCount"] = fail
    family_pk: dict[str, int] = dict(family_totals)
    member_pk_out: dict[tuple[str, str], int] = {}
    for item in summary["ok"]:
        fid = str(item.get("familyId") or "")
        uid = str(item.get("memberUserId") or "")
        r = item.get("result") or {}
        if item.get("status") == "skip":
            member_pk_out[(fid, uid)] = 0
            continue
        member_pk_out[(fid, uid)] = int(r.get("memberPkScore") or item.get("pkDelta") or 0)
    summary["familyPk"] = family_pk
    summary["memberPk"] = {f"{fid}:{uid}": v for (fid, uid), v in member_pk_out.items()}
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["reportPath"] = str(out_path)
    return summary


def datetime_from_iso(text: str):
    from datetime import datetime

    return datetime.strptime(text.strip(), "%Y-%m-%d").date()


def main() -> int:
    parser = argparse.ArgumentParser(description="家族 PK：清 PK → 全员随机 → 平局/双方未达标纠偏")
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET)
    parser.add_argument("--match-sheet", default=DEFAULT_MATCH_SHEET, help="对战来源工作表，默认匹配验收")
    parser.add_argument("--pk-date", required=True)
    parser.add_argument("--max-score", type=int, default=50000)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-clear", action="store_true")
    args = parser.parse_args()

    try:
        summary = run_member_pk_seed(
            workbook=args.workbook.strip(),
            pk_date=args.pk_date.strip(),
            max_score=args.max_score,
            sheet_name=args.sheet_name.strip() or DEFAULT_SHEET,
            match_sheet=args.match_sheet.strip() or DEFAULT_MATCH_SHEET,
            seed=args.seed,
            dry_run=args.dry_run,
            skip_clear=args.skip_clear,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("failedCount", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
