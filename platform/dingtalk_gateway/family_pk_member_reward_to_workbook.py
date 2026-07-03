#!/usr/bin/env python3
"""成员 PK 造数报告 + 匹配列表 → 各用户应得钻石 → 钉钉 Sheet5。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
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

from family_pk_calc_utils import (  # noqa: E402
    compute_member_expected_diamonds,
    load_family_pk_config_from_workbook,
    rename_family_pk_workbook,
    sort_member_reward_rows,
)
from family_pk_tab_to_workbook import (  # noqa: E402
    DEFAULT_WORKBOOK,
    _ensure_sheet,
    _write_sheet_replace,
)
from mse_workbook_utils import fetch_workbook_sheets, node_id  # noqa: E402
from alidocs_excel_export import _excel_env, _get_token_and_operator  # noqa: E402

import httpx  # noqa: E402

DEFAULT_SHEET = "用户发钻测试"
MEMBER_SHEET = "家族列表"
TIER_SHEET = "家族PK档位"
MATCH_SHEET = "匹配验收"
DATA_HEADER = [
    "PK日期",
    "家族ID",
    "家族名称",
    "成员userId",
    "手机号",
    "用户PK值",
    "家族PK值",
    "对手家族ID",
    "对手家族PK值",
    "匹配结果",
    "奖池钻",
    "应得钻石",
    "说明",
]
VERIFY_EXTRA_HEADER = [
    "发奖前钻石",
    "发奖后钻石",
    "实际增量",
    "验收",
]


def _normalize_date(text: str) -> str:
    value = text.strip()
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return value
    raise ValueError(f"日期须为 yyyy-MM-dd: {text!r}")


def _prev_day(pk_date: str) -> str:
    return (datetime.strptime(pk_date, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()


def _cell(row: list[Any], idx: int) -> str:
    if idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


def load_battles_from_match_sheet(
    workbook: str,
    *,
    sheet_name: str = MATCH_SHEET,
) -> tuple[list[dict[str, Any]], list[str]]:
    """从钉钉「匹配验收」读取最新对战/轮空（不依赖造数报告 battlePlans）。"""
    sheets = fetch_workbook_sheets(workbook)
    if sheet_name not in sheets:
        raise RuntimeError(f"未找到工作表: {sheet_name}，请先执行匹配验收步骤")
    battles: list[dict[str, Any]] = []
    bye: list[str] = []
    seen: set[str] = set()
    in_data = False
    for row in sheets[sheet_name]:
        if _cell(row, 0) == "家族ID":
            in_data = True
            continue
        if not in_data:
            continue
        fa = _cell(row, 0)
        if not fa.isdigit() or fa in seen:
            continue
        seen.add(fa)
        fb = _cell(row, 2)
        if fb.isdigit():
            seen.add(fb)
            battles.append({"familyA": fa, "familyB": fb, "scenario": "win"})
        else:
            bye.append(fa)
    if not battles and not bye:
        raise RuntimeError(f"工作表 {sheet_name} 未解析到对战数据")
    return battles, bye


def load_member_directory(
    workbook: str,
    *,
    sheet_name: str = MEMBER_SHEET,
) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    sheets = fetch_workbook_sheets(workbook)
    if sheet_name not in sheets:
        return {}, {}
    family_names: dict[str, str] = {}
    phones: dict[tuple[str, str], str] = {}
    current_fid = ""
    for row in sheets[sheet_name]:
        fid = _cell(row, 0)
        if fid.isdigit():
            current_fid = fid
            family_names[fid] = _cell(row, 1)
        uid = _cell(row, 2)
        phone = _cell(row, 3)
        if uid.isdigit() and current_fid:
            phones[(current_fid, uid)] = phone
    return family_names, phones


def load_family_names(workbook: str, *, sheet_name: str = MEMBER_SHEET) -> dict[str, str]:
    names, _ = load_member_directory(workbook, sheet_name=sheet_name)
    return names


def load_family_tiers_from_workbook(
    workbook: str,
    *,
    sheet_name: str = TIER_SHEET,
    pk_date: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    sheets = fetch_workbook_sheets(workbook)
    if sheet_name not in sheets:
        raise RuntimeError(f"未找到工作表: {sheet_name}，请先执行第三步生成家族PK档位")
    family_tiers: dict[str, list[dict[str, Any]]] = {}
    for row in sheets[sheet_name]:
        fid = _cell(row, 2)
        if not fid.isdigit():
            continue
        try:
            threshold = int(float(_cell(row, 12) or 0))
            diamond = int(float(_cell(row, 14) or 0))
            tier = int(float(_cell(row, 10) or 0))
        except ValueError:
            continue
        if threshold <= 0:
            continue
        family_tiers.setdefault(fid, []).append(
            {"tier": tier, "thresholdPk": threshold, "tierDiamond": diamond}
        )
    for fid in family_tiers:
        family_tiers[fid].sort(key=lambda item: item["thresholdPk"])
    if not family_tiers:
        raise RuntimeError(f"工作表 {sheet_name} 未解析到档位数据")
    return family_tiers


def load_receive_rank(rank_date: str) -> dict[str, dict[str, Any]]:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "MOA/moa_execute.py"),
            "--family-pk-query-receive-rank",
            "--family-pk-date",
            rank_date,
            "--family-pk-limit",
            "500",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "查询收礼榜失败")[-500:])
    body = json.loads(proc.stdout[proc.stdout.find("{") :])
    return {str(x["familyId"]): x for x in body.get("rankList", [])}


def parse_battles_from_plans(battle_plans: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    battles: list[dict[str, Any]] = []
    bye: list[str] = []
    for plan in battle_plans:
        fa = str(plan.get("familyA") or "").strip()
        fb = str(plan.get("familyB") or "").strip() or None
        scenario = str(plan.get("scenario") or "win")
        if fb:
            battles.append({"familyA": fa, "familyB": fb, "scenario": scenario})
        elif fa:
            bye.append(fa)
    return battles, bye


def parse_battles(capture: dict[str, Any], battle_plans: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], list[str]]:
    data = (capture.get("response") or {}).get("data") or {}
    pk_list = data.get("pkList") or []
    plan_map = {}
    if battle_plans:
        for plan in battle_plans:
            key = (plan.get("familyA"), plan.get("familyB"))
            plan_map[key] = plan.get("scenario", "win")
            plan_map[(plan.get("familyB"), plan.get("familyA"))] = plan.get("scenario", "win")

    battles: list[dict[str, Any]] = []
    bye: list[str] = []
    seen: set[str] = set()
    for pair in pk_list:
        if not isinstance(pair, dict):
            continue
        fa_info = pair.get("familyInfo") or {}
        opp = pair.get("opponentFamily")
        fa = str(fa_info.get("familyId") or "").strip()
        if not fa.isdigit() or fa in seen:
            continue
        seen.add(fa)
        if isinstance(opp, dict) and opp.get("familyId"):
            fb = str(opp.get("familyId")).strip()
            seen.add(fb)
            scenario = plan_map.get((fa, fb), "win")
            battles.append({"familyA": fa, "familyB": fb, "scenario": scenario})
        else:
            bye.append(fa)
    return battles, bye


def load_pk_from_seed_report(report_path: Path) -> tuple[dict[tuple[str, str], int], dict[str, int], list[dict[str, Any]]]:
    data = json.loads(report_path.read_text(encoding="utf-8"))
    member_pk: dict[tuple[str, str], int] = {}
    family_pk: dict[str, int] = {}
    for item in data.get("ok") or []:
        result = item.get("result") or {}
        fid = str(result.get("familyId") or item.get("familyId") or "")
        uid = str(result.get("memberUserId") or item.get("memberUserId") or "")
        if not fid or not uid:
            continue
        member_pk[(fid, uid)] = int(result.get("memberPkScore") or item.get("pkDelta") or 0)
        family_pk[fid] = max(family_pk.get(fid, 0), int(result.get("familyPkScore") or 0))
    if not member_pk and data.get("assignments"):
        for item in data["assignments"]:
            fid = str(item.get("familyId") or "")
            uid = str(item.get("memberUserId") or "")
            if not fid or not uid:
                continue
            delta = int(item.get("pkDelta") or 0)
            member_pk[(fid, uid)] = delta
            family_pk[fid] = family_pk.get(fid, 0) + delta
    if not member_pk and data.get("memberPk"):
        for key, value in data["memberPk"].items():
            fid, uid = key.split(":", 1)
            member_pk[(fid, uid)] = int(value)
    if not family_pk and data.get("familyPk"):
        family_pk = {str(k): int(v) for k, v in data["familyPk"].items()}
    battle_plans = data.get("battlePlans") or []
    return member_pk, family_pk, battle_plans


def build_reward_sheet_rows(
    *,
    pk_date: str,
    family_names: dict[str, str],
    member_phones: dict[tuple[str, str], str],
    member_rows: list[dict[str, Any]],
    unmatched_members: list[dict[str, Any]],
) -> list[list[Any]]:
    rows: list[list[Any]] = [
        [
            "测算摘要",
            f"PK日期={pk_date}",
            f"成员行数={len(member_rows) + len(unmatched_members)}",
            f"应发钻合计={sum(int(r.get('expectedDiamond') or 0) for r in member_rows + unmatched_members)}",
            "",
            "",
        ],
        [
            "规则说明",
            "胜方家族PK≥minWinPk 才发钻",
            "平局或胜方未达标不发钻",
            "用户PK≥minRewardPk 才参与瓜分",
            "应得=(用户PK/家族PK)*奖池，向下取整",
            "奖池=双方档位钻石之和，未达档用basePool",
            "",
        ],
        [],
        DATA_HEADER,
    ]
    for item in sort_member_reward_rows(member_rows + unmatched_members):
        fid = str(item.get("familyId") or "")
        uid = str(item.get("userId") or "")
        rows.append(
            [
                pk_date,
                fid,
                family_names.get(fid, ""),
                uid,
                member_phones.get((fid, uid), ""),
                item.get("memberPk", 0),
                item.get("familyPk", 0),
                item.get("opponentFamilyId", ""),
                item.get("opponentFamilyPk", 0),
                item.get("matchResult", ""),
                item.get("poolDiamond", 0),
                item.get("expectedDiamond", 0),
                item.get("note", ""),
            ]
        )
    return rows


def compute_member_reward_rows(
    *,
    workbook: str,
    pk_date: str,
    seed_report: Path | None = None,
    tier_sheet: str = TIER_SHEET,
    match_sheet: str = MATCH_SHEET,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[tuple[str, str], str]]:
    """根据造数 PK + 匹配验收最新对战，按家族总 PK 重算胜负与应得钻石。"""
    pk_date = _normalize_date(pk_date)
    report_path = seed_report or (REPO_ROOT / ".tmp" / f"family_pk_member_pk_seed_{pk_date}.json")
    if not report_path.is_file():
        raise RuntimeError(f"未找到造数报告: {report_path}，请先执行第五步 family_pk_member_pk_seed.py")

    member_pk, family_pk, _battle_plans = load_pk_from_seed_report(report_path)
    config = load_family_pk_config_from_workbook(workbook)
    seed_data = json.loads(report_path.read_text(encoding="utf-8"))
    battles, bye = load_battles_from_match_sheet(workbook, sheet_name=match_sheet)
    family_tiers = load_family_tiers_from_workbook(workbook, sheet_name=tier_sheet, pk_date=pk_date)
    family_names, member_phones = load_member_directory(workbook)

    _, member_rows = compute_member_expected_diamonds(
        battles=battles,
        bye_families=bye,
        member_pk=member_pk,
        family_pk=family_pk,
        family_tiers=family_tiers,
        config=config,
    )
    covered_users = {str(r["userId"]) for r in member_rows}
    assignments = seed_data.get("assignments") or []
    unmatched = build_unmatched_rows(
        member_pk=member_pk,
        family_pk=family_pk,
        covered_users=covered_users,
        family_names=family_names,
        assignments=assignments,
    )
    return sort_member_reward_rows(member_rows + unmatched), family_names, member_phones


def build_unmatched_rows(
    *,
    member_pk: dict[tuple[str, str], int],
    family_pk: dict[str, int],
    covered_users: set[str],
    family_names: dict[str, str],
    assignments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    assignment_map = {
        (str(a["familyId"]), str(a["memberUserId"])): a.get("scenario", "random")
        for a in assignments
    }
    rows: list[dict[str, Any]] = []
    for (fid, uid), mpk in member_pk.items():
        if uid in covered_users:
            continue
        rows.append(
            {
                "familyId": fid,
                "userId": uid,
                "memberPk": mpk,
                "familyPk": family_pk.get(fid, 0),
                "opponentFamilyId": "",
                "opponentFamilyPk": 0,
                "matchResult": "无匹配",
                "scenario": assignment_map.get((fid, uid), "random"),
                "poolDiamond": 0,
                "minRewardPk": "",
                "expectedDiamond": 0,
                "note": "当日无对战匹配",
            }
        )
    return rows


async def write_reward_sheet_async(
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


def export_member_reward_to_workbook(
    *,
    workbook: str,
    pk_date: str,
    momoid: str,
    since: int,
    seed_report: Path | None,
    sheet_name: str,
    tier_sheet: str,
    match_sheet: str,
) -> dict[str, Any]:
    pk_date = _normalize_date(pk_date)
    rank_date = _prev_day(pk_date)
    member_rows, family_names, member_phones = compute_member_reward_rows(
        workbook=workbook,
        pk_date=pk_date,
        seed_report=seed_report,
        tier_sheet=tier_sheet,
        match_sheet=match_sheet,
    )
    report_path = seed_report or (REPO_ROOT / ".tmp" / f"family_pk_member_pk_seed_{pk_date}.json")
    seed_data = json.loads(report_path.read_text(encoding="utf-8"))
    battles, bye = load_battles_from_match_sheet(workbook, sheet_name=match_sheet)

    sheet_rows = build_reward_sheet_rows(
        pk_date=pk_date,
        family_names=family_names,
        member_phones=member_phones,
        member_rows=member_rows,
        unmatched_members=[],
    )
    doc_url = asyncio.run(write_reward_sheet_async(workbook, sheet_rows, sheet_name=sheet_name))
    workbook_title = rename_family_pk_workbook(workbook, pk_date)

    summary = {
        "pkDate": pk_date,
        "rankDate": rank_date,
        "memberCount": int(seed_data.get("memberCount") or len(member_rows)),
        "familyCount": int(seed_data.get("familyCount") or 0),
        "battleCount": len(battles),
        "byeCount": len(bye),
        "rewardRows": len(member_rows),
        "expectedTotal": sum(int(r.get("expectedDiamond") or 0) for r in member_rows),
        "scenarioStats": {
            s: sum(1 for r in member_rows if r.get("scenario") == s)
            for s in ["win", "tie", "pk_low", "member_low", "lose", "bye_win", "bye_pk_low"]
        },
        "workbookUrl": doc_url,
        "workbookTitle": workbook_title,
        "sheetName": sheet_name,
        "matchSheet": match_sheet,
        "battleSource": "match_sheet",
        "seedReport": str(report_path),
    }
    out_path = REPO_ROOT / ".tmp" / f"family_pk_member_reward_{pk_date}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["reportPath"] = str(out_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="家族 PK 用户应得钻石测算 → 钉钉 Sheet5")
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK)
    parser.add_argument("--pk-date", required=True)
    parser.add_argument("--momoid", default="100465989")
    parser.add_argument("--since", type=int, default=259200)
    parser.add_argument("--seed-report", type=Path, help="family_pk_member_pk_seed 报告路径")
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET)
    parser.add_argument("--match-sheet", default=MATCH_SHEET, help="对战来源工作表，默认匹配验收")
    parser.add_argument("--tier-sheet", default=TIER_SHEET, help="档位钻石来源 Sheet")
    args = parser.parse_args()

    try:
        summary = export_member_reward_to_workbook(
            workbook=args.workbook.strip(),
            pk_date=args.pk_date.strip(),
            momoid=str(args.momoid).strip(),
            since=args.since,
            seed_report=args.seed_report,
            sheet_name=args.sheet_name.strip() or DEFAULT_SHEET,
            tier_sheet=args.tier_sheet.strip() or TIER_SHEET,
            match_sheet=args.match_sheet.strip() or MATCH_SHEET,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
