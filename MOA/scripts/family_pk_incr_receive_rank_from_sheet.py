#!/usr/bin/env python3
"""按钉钉家族表为昨日收礼日榜随机增加 0~max_delta 收礼值（覆盖写 after=before+delta）。"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from moa_script_paths import moa_execute_path, repo_root, tmp_dir

_DEFAULT_SHEET = (
    tmp_dir()
    / "family-pk-list/家族成员全量含手机号-20260625-165701.axls/93NwLYZXWyg4ozlzCNanyzR4JkyEqBQm_content.json"
)


def _load_families(sheet_path: Path) -> dict[str, str]:
    with open(sheet_path, encoding="utf-8") as f:
        data = json.load(f)
    families: dict[str, str] = {}
    for row in data["content"]["kgqie6hm"]["rows"]:
        if len(row) < 3 or not isinstance(row[2], list):
            continue
        cells = {
            col: (cell.get("value") if isinstance(cell, dict) else cell)
            for col, cell in row[2]
        }
        fid = str(cells.get(0) or "").strip()
        if fid.isdigit() and fid not in families:
            families[fid] = str(cells.get(1) or "")
    if not families:
        raise RuntimeError(f"钉钉表未解析到家族: {sheet_path}")
    return families


def _query_raw_rank_map(rank_date: str) -> dict[str, int]:
    proc = subprocess.run(
        [
            "python3",
            str(moa_execute_path()),
            "--family-pk-query-receive-rank",
            "--family-pk-date",
            rank_date,
            "--family-pk-limit",
            "500",
            "--family-pk-include-dissolved",
        ],
        cwd=str(repo_root()),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-500:]
        raise RuntimeError(f"查询收礼日榜失败: {tail}")
    body = json.loads(proc.stdout[proc.stdout.find("{") :])
    return {
        str(x["familyId"]): int(x.get("receiveScore") or 0)
        for x in body.get("rawRankList", [])
    }


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
    payload_path = tmp_dir() / f"modify_rank_{family_id}.json"
    payload_path.parent.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(json.dumps(tpl, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        ["python3", str(moa_execute_path()), "--payload-file", str(payload_path)],
        cwd=str(repo_root()),
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


def main() -> int:
    parser = argparse.ArgumentParser(description="钉钉家族表昨日收礼榜随机增量造数")
    parser.add_argument("--sheet-json", type=Path, default=_DEFAULT_SHEET, help="钉钉表 content.json 路径")
    parser.add_argument("--date", help="收礼日榜日期 yyyy-MM-dd（默认昨日）")
    parser.add_argument("--max-delta", type=int, default=50000, help="随机增量上限（含 0，默认 50000）")
    parser.add_argument("--seed", type=int, help="随机种子（可复现）")
    parser.add_argument("--dry-run", action="store_true", help="仅生成计划，不调用 MOA 写入")
    parser.add_argument("--assignments-file", type=Path, help="从已有计划文件执行（跳过随机）")
    args = parser.parse_args()

    rank_date = (args.date or (date.today() - timedelta(days=1)).isoformat()).strip()
    if args.max_delta < 0:
        print("--max-delta 不能为负", file=sys.stderr)
        return 2

    if args.assignments_file:
        plan = json.loads(args.assignments_file.read_text(encoding="utf-8"))
        raw_assignments = plan.get("assignments") or plan
        if not isinstance(raw_assignments, list):
            print("assignments 文件格式错误", file=sys.stderr)
            return 2
        current = {} if args.dry_run else _query_raw_rank_map(rank_date)
        assignments = []
        for item in raw_assignments:
            fid = str(item["familyId"])
            delta = int(item["delta"])
            before = int(current.get(fid, item.get("before", 0)))
            assignments.append(
                {
                    "familyId": fid,
                    "familyName": str(item.get("familyName") or ""),
                    "before": before,
                    "delta": delta,
                    "after": before + delta,
                }
            )
    else:
        families = _load_families(args.sheet_json)
        if args.seed is not None:
            random.seed(args.seed)
        current = {} if args.dry_run else _query_raw_rank_map(rank_date)
        assignments = []
        for fid, name in sorted(families.items(), key=lambda x: int(x[0])):
            before = int(current.get(fid, 0))
            delta = random.randint(0, args.max_delta)
            assignments.append(
                {
                    "familyId": fid,
                    "familyName": name,
                    "before": before,
                    "delta": delta,
                    "after": before + delta,
                }
            )

    out_path = tmp_dir() / f"family_receive_rank_incr_{rank_date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "date": rank_date,
        "maxDelta": args.max_delta,
        "source": str(args.sheet_json),
        "assignments": assignments,
    }

    if args.dry_run:
        summary["dryRun"] = True
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"date": rank_date, "count": len(assignments), "out": str(out_path)}, ensure_ascii=False))
        return 0

    ok = fail = 0
    for item in assignments:
        fid = str(item["familyId"])
        after = int(item["after"])
        try:
            result = _modify_rank(rank_date, fid, after)
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
            if "SSO" in str(exc) or "Cookie" in str(exc) or "合法 JSON" in str(exc):
                summary.update({"ok": ok, "fail": fail, "aborted": True})
                out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
                print(
                    f"MOA Cookie 可能已过期，已写入 {ok} 条后中止。请更新 MOA/.env.local 的 MOA_COOKIE 后重跑:\n"
                    f"  python3 MOA/scripts/family_pk_incr_receive_rank_from_sheet.py "
                    f"--assignments-file {out_path}",
                    file=sys.stderr,
                )
                return 1

    summary.update({"ok": ok, "fail": fail})
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"date": rank_date, "ok": ok, "fail": fail, "out": str(out_path)}, ensure_ascii=False))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
