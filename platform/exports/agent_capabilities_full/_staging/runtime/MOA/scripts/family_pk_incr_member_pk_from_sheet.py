#!/usr/bin/env python3
"""按钉钉家族表为全部成员昨日家族 PK 值随机增加 min~max_delta。"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_SHEET = (
    _REPO
    / ".tmp/family-pk-list/家族成员全量含手机号-20260625-165701.axls/93NwLYZXWyg4ozlzCNanyzR4JkyEqBQm_content.json"
)


def _load_members(sheet_path: Path) -> list[dict[str, str]]:
    with open(sheet_path, encoding="utf-8") as f:
        data = json.load(f)
    members: list[dict[str, str]] = []
    current_fid: str | None = None
    current_name = ""
    for row in data["content"]["kgqie6hm"]["rows"]:
        if len(row) < 3 or not isinstance(row[2], list):
            continue
        cells = {
            col: (cell.get("value") if isinstance(cell, dict) else cell)
            for col, cell in row[2]
        }
        fid = str(cells.get(0) or "").strip()
        if fid.isdigit():
            current_fid = fid
            current_name = str(cells.get(1) or "")
        uid = str(cells.get(5) or "").strip()
        if uid.isdigit() and current_fid:
            members.append(
                {
                    "familyId": current_fid,
                    "familyName": current_name,
                    "memberUserId": uid,
                }
            )
    if not members:
        raise RuntimeError(f"钉钉表未解析到成员: {sheet_path}")
    return members


def _incr_pk(rank_date: str, family_id: str, member_user_id: str, pk_delta: int) -> dict[str, Any]:
    body = {
        "lang": "zh",
        "date": rank_date,
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
        "settings": {
            "time": 2000,
            "group": "default",
            "host": "",
            "headerType": "TXT",
        },
        "region": "alpha",
        "env": "alpha",
        "cluster": "stage",
        "server": "config",
        "momoId": "df4c6f364f9fcae3",
        "momoName": "e88ea376b29864ad",
    }
    payload_path = _REPO / ".tmp" / f"incr_pk_{family_id}_{member_user_id}.json"
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(json.dumps(tpl, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        ["python3", str(_REPO / "MOA/moa_execute.py"), "--payload-file", str(payload_path)],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "MOA 调用失败")[-500:])
    resp = json.loads(proc.stdout[proc.stdout.find("{") :])
    inner_wrap = resp.get("result", {}).get("result", {})
    inner = inner_wrap.get("data") if isinstance(inner_wrap, dict) else None
    if inner is None and isinstance(inner_wrap, dict):
        inner = inner_wrap
    if not isinstance(inner, dict):
        return {"ok": False, "response": inner_wrap}
    return {"ok": True, "result": inner}


def main() -> int:
    parser = argparse.ArgumentParser(description="钉钉表成员昨日家族 PK 值随机增量造数")
    parser.add_argument("--sheet-json", type=Path, default=_DEFAULT_SHEET)
    parser.add_argument("--date", help="PK 日期 yyyy-MM-dd（默认昨日）")
    parser.add_argument("--min-delta", type=int, default=100)
    parser.add_argument("--max-delta", type=int, default=50000)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--assignments-file", type=Path)
    args = parser.parse_args()

    rank_date = (args.date or (date.today() - timedelta(days=1)).isoformat()).strip()
    if args.min_delta < 0 or args.max_delta < args.min_delta:
        print("delta 范围无效", file=sys.stderr)
        return 2

    if args.assignments_file:
        plan = json.loads(args.assignments_file.read_text(encoding="utf-8"))
        assignments = plan.get("assignments") or plan.get("ok") or plan
        if not isinstance(assignments, list):
            print("assignments 文件格式错误", file=sys.stderr)
            return 2
    else:
        members = _load_members(args.sheet_json)
        if args.seed is not None:
            random.seed(args.seed)
        assignments = []
        for m in members:
            assignments.append(
                {
                    **m,
                    "pkDelta": random.randint(args.min_delta, args.max_delta),
                }
            )

    out_path = _REPO / ".tmp" / f"family_pk_member_incr_{rank_date}.json"
    summary: dict[str, Any] = {
        "summary": {
            "date": rank_date,
            "members": len(assignments),
            "families": len({a["familyId"] for a in assignments}),
            "minDelta": args.min_delta,
            "maxDelta": args.max_delta,
        },
        "assignments": assignments,
        "ok": [],
        "failed": [],
    }

    if args.dry_run:
        summary["summary"]["dryRun"] = True
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"date": rank_date, "members": len(assignments), "out": str(out_path)}, ensure_ascii=False))
        return 0

    ok = fail = 0
    for item in assignments:
        fid = str(item["familyId"])
        uid = str(item["memberUserId"])
        delta = int(item["pkDelta"])
        rec = dict(item)
        try:
            result = _incr_pk(rank_date, fid, uid, delta)
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
            if "SSO" in str(exc) or "Cookie" in str(exc) or "合法 JSON" in str(exc):
                summary["summary"].update({"success": ok, "failed": fail, "aborted": True})
                out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"MOA 异常中止，已成功 {ok} 条。明细: {out_path}", file=sys.stderr)
                return 1

    summary["summary"].update({"success": ok, "failed": fail})
    if summary["ok"]:
        deltas = [int(x["pkDelta"]) for x in summary["ok"]]
        summary["summary"]["pkDeltaMin"] = min(deltas)
        summary["summary"]["pkDeltaMax"] = max(deltas)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"date": rank_date, "ok": ok, "fail": fail, "out": str(out_path)}, ensure_ascii=False))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
