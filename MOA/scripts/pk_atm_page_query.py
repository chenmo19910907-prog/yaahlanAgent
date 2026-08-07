#!/usr/bin/env python3
"""PK 提款机活动页：本周总下发钻石 + 提款排行榜（getAcrossPkRewardRankV2）。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SERVICE = "/service/room/external/room-pk-api"
METHOD = "getAcrossPkRewardRankV2"
CYCLE_CURRENT = "1"
CYCLE_PRE = "2"


def _run_moa(body: dict[str, Any]) -> dict[str, Any]:
    tmp = REPO / ".tmp" / "pk_atm_page"
    tmp.mkdir(parents=True, exist_ok=True)
    body_file = tmp / "rank.body.json"
    body_file.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO / "MOA-generative/scripts/run_generative_moa.py"),
            "--url",
            SERVICE,
            "--method",
            METHOD,
            "--body-file",
            str(body_file),
            "--strict",
            "0",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "MOA 调用失败").strip())
    return json.loads(proc.stdout)


def _business_data(resp: dict[str, Any]) -> dict[str, Any]:
    biz = resp.get("business") or {}
    ec = biz.get("ec")
    if ec not in (200, "200", 0, "0"):
        raise RuntimeError(f"业务失败 ec={ec} em={biz.get('em')}")
    data = biz.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("response.data 不是对象")
    return data


def _parse_user_id_from_moa_stdout(raw: str) -> str:
    decoder = json.JSONDecoder()
    idx = 0
    payloads: list[dict[str, Any]] = []
    while idx < len(raw):
        start = raw.find("{", idx)
        if start < 0:
            break
        try:
            payload, end = decoder.raw_decode(raw, start)
        except json.JSONDecodeError:
            idx = start + 1
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
        idx = end
    for payload in reversed(payloads):
        uid = payload.get("userId")
        if uid:
            return str(uid)
        inner = payload.get("result")
        if isinstance(inner, dict):
            nested = inner.get("result")
            if isinstance(nested, dict) and nested.get("data"):
                return str(nested["data"])
    raise RuntimeError(f"未解析到 userId: {raw[-500:]}")


def _resolve_user_id(args: argparse.Namespace) -> str:
    if args.user_id:
        return str(args.user_id).strip()
    if args.phone:
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO / "MOA/moa_execute.py"),
                "--payload-file",
                str(REPO / "MOA/templates/用户-按手机号查userId.json"),
                "--query-user-by-phone",
                str(args.phone).strip(),
                "--phone-output",
                "summary",
            ],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=60,
        )
        merged = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "手机号查 userId 失败").strip())
        return _parse_user_id_from_moa_stdout(merged)
    raise SystemExit("必须提供 --user-id 或 --phone")


def query_pk_atm_page(*, user_id: str, cycle: str = CYCLE_CURRENT, area: str = "MENA") -> dict[str, Any]:
    body = {
        "userId": user_id,
        "uid": user_id,
        "cycle": cycle,
        "lang": "en",
        "area": area.upper(),
        "appId": "2005",
        "os": "android",
        "osType": "android",
        "originRsp": 1,
        "dataType": "json",
        "_version_": 1000,
    }
    data = _business_data(_run_moa(body))
    rank_list = data.get("list") if isinstance(data.get("list"), list) else []
    top = []
    for item in rank_list[:50]:
        if not isinstance(item, dict):
            continue
        top.append(
            {
                "rank": item.get("rank"),
                "userId": item.get("userId"),
                "nickname": item.get("nickname"),
                "rewardValue": item.get("rewardValue"),
                "roomId": item.get("roomId"),
            }
        )
    current = data.get("currentUser") if isinstance(data.get("currentUser"), dict) else None
    return {
        "userId": user_id,
        "cycle": cycle,
        "weekTotalWithdrawDiamonds": data.get("totalReward"),
        "minTotalPkValue": data.get("minTotalPkValue"),
        "minMemberRewardPk": data.get("minMemberRewardPk"),
        "residueTimeSec": data.get("residueTime"),
        "rankList": top,
        "currentUser": current,
        "method": f"{SERVICE}#{METHOD}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PK 提款机活动页：本周总钻石 + 提款排行榜")
    parser.add_argument("--user-id", help="userId")
    parser.add_argument("--phone", help="手机号（+86）")
    parser.add_argument("--cycle", default=CYCLE_CURRENT, help="1=本周 2=上周（默认 1）")
    parser.add_argument("--area", default="MENA")
    parser.add_argument("--top", type=int, default=10, help="摘要展示前 N 名")
    args = parser.parse_args()
    uid = _resolve_user_id(args)
    out = query_pk_atm_page(user_id=uid, cycle=str(args.cycle), area=args.area)
    if args.top and isinstance(out.get("rankList"), list):
        out["rankListPreview"] = out["rankList"][: max(0, args.top)]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
