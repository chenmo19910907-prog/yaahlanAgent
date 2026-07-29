#!/usr/bin/env python3
"""查询用户钻石记录（diamondHistory）：Tunnel 抓包 → MOA-generative 执行。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_SERVICE_URL = "/service/yaahlan/components/wallet-api"
_METHOD = "diamondHistory"
_TEMPLATE_BODY = _REPO / "MOA-generative/templates/example-diamondHistory.body.json"


def _build_body(user_id: str, template: dict[str, Any], *, page_size: int, last_id: str, record_type: str) -> dict[str, Any]:
    body = dict(template)
    body["userId"] = user_id
    body["uid"] = user_id
    body["pageSize"] = str(page_size)
    body["lastId"] = str(last_id)
    body["type"] = record_type
    return body


def _summarize_records(business: dict[str, Any]) -> dict[str, Any]:
    data = business.get("data")
    if not isinstance(data, dict):
        return {"parsed": False, "raw": business}
    items = data.get("list") if isinstance(data.get("list"), list) else []
    recent = []
    for item in items[:5]:
        if not isinstance(item, dict):
            continue
        recent.append(
            {
                "desc": item.get("desc"),
                "rechargeMethod": item.get("rechargeMethod"),
                "diamondDiff": item.get("diamondDiff"),
                "diamondAccount": item.get("diamondAccount"),
                "createTime": item.get("createTime"),
                "orderId": item.get("orderId"),
            }
        )
    return {
        "parsed": True,
        "count": len(items),
        "lastId": data.get("lastId"),
        "hasMore": data.get("hasMore"),
        "recent": recent,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="MOA 查询用户钻石记录")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--last-id", default="0")
    parser.add_argument("--type", dest="record_type", default="", help="记录类型筛选，默认空")
    parser.add_argument("--service-url", default=_SERVICE_URL)
    parser.add_argument("--strict", type=int, default=1, choices=(0, 1))
    parser.add_argument("--timeout-ms", type=int, default=20000)
    args = parser.parse_args()

    template = json.loads(_TEMPLATE_BODY.read_text(encoding="utf-8"))
    user_id = str(args.user_id).strip()
    body = _build_body(
        user_id,
        template,
        page_size=max(1, int(args.page_size)),
        last_id=str(args.last_id),
        record_type=str(args.record_type or ""),
    )
    body_path = _REPO / ".tmp" / f"diamond_history_{user_id}.body.json"
    payload_path = _REPO / ".tmp" / f"diamond_history_{user_id}.payload.json"
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    proc = subprocess.run(
        [
            "python3",
            str(_REPO / "MOA-generative/scripts/run_generative_moa.py"),
            "--url",
            args.service_url,
            "--method",
            _METHOD,
            "--body-file",
            str(body_path),
            "--out",
            str(payload_path),
            "--timeout-ms",
            str(args.timeout_ms),
            "--strict",
            str(args.strict),
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = (proc.stdout or "").strip()
    if "{" not in stdout:
        print(
            json.dumps(
                {"ok": False, "error": "run_generative_moa 无 JSON 输出", "stderr": (proc.stderr or "")[-500:]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    summary = json.loads(stdout[stdout.find("{") :])
    business = summary.get("business") if isinstance(summary.get("business"), dict) else {}
    summary["recordSummary"] = _summarize_records(business)
    summary["bodyFile"] = str(body_path)
    summary["payloadFile"] = str(payload_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
