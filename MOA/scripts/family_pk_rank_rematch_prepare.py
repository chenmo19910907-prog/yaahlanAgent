#!/usr/bin/env python3
"""钉钉家族列表 → 指定日期收礼榜随机造数 → 清除并重匹配次日 PK。"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_GATEWAY = _REPO / "platform" / "dingtalk_gateway"
if str(_GATEWAY) not in sys.path:
    sys.path.insert(0, str(_GATEWAY))

from mse_workbook_utils import fetch_workbook_sheets_async, node_id  # noqa: E402

DEFAULT_WORKBOOK = "https://alidocs.dingtalk.com/i/nodes/N7dx2rn0JbZQqA9ACZ1MoaaRJMGjLRb3"
DEFAULT_SHEET = "家族列表"
LARGE_FAMILY_MIN_MEMBERS = 11  # 大于 10 人
LARGE_SCORE_MIN = 200_000
LARGE_SCORE_MAX = 1_000_000
SMALL_SCORE_MIN = 0
SMALL_SCORE_MAX = 200_000


def _cell(row: list[Any], idx: int) -> str:
    if idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


async def load_families_from_workbook(
    workbook_url_or_id: str,
    *,
    sheet_name: str = DEFAULT_SHEET,
) -> list[dict[str, Any]]:
    """解析家族列表：每个家族含 familyId、familyName、memberCount。"""
    workbook_id = node_id(workbook_url_or_id)
    url = f"https://alidocs.dingtalk.com/i/nodes/{workbook_id}"
    sheets = await fetch_workbook_sheets_async(url)
    if sheet_name not in sheets:
        raise RuntimeError(f"未找到工作表: {sheet_name}")
    families: dict[str, dict[str, Any]] = {}
    current_fid = ""
    current_name = ""
    for row in sheets[sheet_name]:
        fid = _cell(row, 0)
        if fid.isdigit():
            current_fid = fid
            current_name = _cell(row, 1)
            if fid not in families:
                families[fid] = {
                    "familyId": fid,
                    "familyName": current_name,
                    "memberCount": 0,
                }
        uid = _cell(row, 2)
        if uid.isdigit() and current_fid and current_fid in families:
            families[current_fid]["memberCount"] += 1
    if not families:
        raise RuntimeError(f"工作表 {sheet_name} 未解析到家族 ID")
    return sorted(families.values(), key=lambda x: int(x["familyId"]))


def load_families_from_workbook_sync(workbook: str, *, sheet_name: str) -> list[dict[str, Any]]:
    return asyncio.run(load_families_from_workbook(workbook, sheet_name=sheet_name))


def _score_range_for_family(member_count: int) -> tuple[int, int, str]:
    """按成员数返回 (min, max, tier)。"""
    if member_count > LARGE_FAMILY_MIN_MEMBERS - 1:
        return LARGE_SCORE_MIN, LARGE_SCORE_MAX, "large"
    return SMALL_SCORE_MIN, SMALL_SCORE_MAX, "small"


def _modify_rank(rank_date: str, family_id: str, score: int) -> dict[str, Any]:
    body = {
        "lang": "zh",
        "date": rank_date,
        "familyId": family_id,
        "familyReceiveScore": score,
    }
    tpl = {
        "type": "moa",
        "key": "momo.pt.toB.cosmos-server.quality-platform.codequality",
        "url": "/service/vas/internal/family-pk-moa",
        "method": "modifyReceiveDailyRankForTest",
        "header": "",
        "params": [
            {
                "name": 0,
                "title": "",
                "txt": "",
                "json": json.dumps(body, ensure_ascii=False),
                "type": "json",
                "value": body,
            }
        ],
        "settings": {"time": 2000, "group": "default", "host": "", "headerType": "TXT"},
        "region": "alpha",
        "env": "alpha",
        "cluster": "stage",
        "server": "config",
        "momoId": "df4c6f364f9fcae3",
        "momoName": "e88aa376b29864ad",
    }
    payload_path = _REPO / ".tmp" / f"modify_rank_{family_id}_{rank_date}.json"
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(json.dumps(tpl, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(_REPO / "MOA/moa_execute.py"), "--payload-file", str(payload_path)],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "MOA 调用失败")[-500:])
    resp = json.loads(proc.stdout[proc.stdout.find("{") :])
    inner = resp.get("result", {}).get("result", {})
    if inner.get("success") is True or inner.get("data") is True:
        return {"ok": True, "response": inner}
    return {"ok": False, "response": inner}


def _run_rematch(pk_date: str, timeout_ms: int) -> dict[str, Any]:
    proc = subprocess.run(
        [
            sys.executable,
            str(_REPO / "workflow/workflow_execute.py"),
            "run",
            "family-pk-daily-rematch",
            "--pk-date",
            pk_date,
            "--timeout-ms",
            str(timeout_ms),
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=max(300, timeout_ms // 1000 + 120),
        check=False,
    )
    text = (proc.stdout or "").strip()
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or text or "重匹配工作流失败")[-800:])
    start = text.find("{")
    end = text.rfind("}")
    if start < 0:
        return {"ok": True, "raw": text}
    return json.loads(text[start : end + 1])


def _next_day(rank_date: str) -> str:
    return (datetime.strptime(rank_date, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()


def run_prepare(
    *,
    workbook: str,
    sheet_name: str,
    rank_date: str,
    pk_date: str | None,
    seed: int | None,
    timeout_ms: int,
    dry_run: bool,
    skip_rematch: bool,
) -> dict[str, Any]:
    families = load_families_from_workbook_sync(workbook, sheet_name=sheet_name)
    if seed is None:
        seed = int(rank_date.replace("-", ""))
    rng = random.Random(seed)

    assignments: list[dict[str, Any]] = []
    tier_stats = {"large": 0, "small": 0}
    for fam in families:
        fid = str(fam["familyId"])
        name = str(fam["familyName"])
        member_count = int(fam["memberCount"])
        score_min, score_max, tier = _score_range_for_family(member_count)
        tier_stats[tier] += 1
        score = rng.randint(score_min, score_max)
        assignments.append(
            {
                "familyId": fid,
                "familyName": name,
                "memberCount": member_count,
                "scoreTier": tier,
                "scoreRange": f"{score_min}-{score_max}",
                "receiveScore": score,
                "onRank": score > 0,
            }
        )

    out_path = _REPO / ".tmp" / f"family_receive_rank_set_{rank_date}.json"
    summary: dict[str, Any] = {
        "rankDate": rank_date,
        "pkDate": pk_date or _next_day(rank_date),
        "seed": seed,
        "scoreRules": {
            "large": {
                "memberCount": f">{LARGE_FAMILY_MIN_MEMBERS - 1}",
                "min": LARGE_SCORE_MIN,
                "max": LARGE_SCORE_MAX,
            },
            "small": {
                "memberCount": f"<={LARGE_FAMILY_MIN_MEMBERS - 1}",
                "min": SMALL_SCORE_MIN,
                "max": SMALL_SCORE_MAX,
            },
        },
        "tierStats": tier_stats,
        "workbook": workbook,
        "sheetName": sheet_name,
        "familyCount": len(assignments),
        "assignments": assignments,
    }

    if dry_run:
        summary["dryRun"] = True
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        summary["reportPath"] = str(out_path)
        return summary

    ok = fail = skipped = 0
    for item in assignments:
        fid = str(item["familyId"])
        score = int(item["receiveScore"])
        if score <= 0:
            skipped += 1
            item["status"] = "skip_zero"
            continue
        try:
            result = _modify_rank(rank_date, fid, score)
            if result["ok"]:
                ok += 1
                item["status"] = "ok"
            else:
                fail += 1
                item["status"] = "fail"
                item["response"] = result["response"]
        except RuntimeError as exc:
            fail += 1
            item["status"] = "error"
            item["error"] = str(exc)
            if "SSO" in str(exc) or "Cookie" in str(exc):
                summary.update({"writeOk": ok, "writeFail": fail, "writeSkip": skipped, "aborted": True})
                out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
                raise

    summary.update({"writeOk": ok, "writeFail": fail, "writeSkip": skipped})
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["reportPath"] = str(out_path)

    if fail > 0:
        raise RuntimeError(f"收礼榜写入失败 {fail} 条，详见 {out_path}")

    if not skip_rematch:
        rematch_pk_date = pk_date or _next_day(rank_date)
        summary["rematch"] = _run_rematch(rematch_pk_date, timeout_ms)

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="家族收礼榜按人数分段随机造数并重匹配次日PK"
    )
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK, help="钉钉表格 URL/nodeId")
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET, help="家族列表工作表")
    parser.add_argument("--rank-date", default="2026-07-01", help="收礼日榜日期 yyyy-MM-dd")
    parser.add_argument(
        "--pk-date",
        help="重匹配 PK 日期（默认 rank-date 次日）",
    )
    parser.add_argument("--seed", type=int, help="随机种子（默认 rank-date 数字）")
    parser.add_argument("--timeout-ms", type=int, default=180000, help="runFamilyPkMatchTask 超时")
    parser.add_argument("--dry-run", action="store_true", help="仅生成计划不写榜、不重匹配")
    parser.add_argument("--skip-rematch", action="store_true", help="仅写收礼榜，不重匹配")
    args = parser.parse_args()

    try:
        summary = run_prepare(
            workbook=args.workbook.strip(),
            sheet_name=args.sheet_name.strip() or DEFAULT_SHEET,
            rank_date=args.rank_date.strip(),
            pk_date=args.pk_date.strip() if args.pk_date else None,
            seed=args.seed,
            timeout_ms=args.timeout_ms,
            dry_run=args.dry_run,
            skip_rematch=args.skip_rematch,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
