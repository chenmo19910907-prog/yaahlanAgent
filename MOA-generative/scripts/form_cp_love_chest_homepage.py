#!/usr/bin/env python3
"""查询 CP 爱意宝箱主页（getCpLoveChestHomepage）：Tunnel 抓包 → MOA-generative 执行。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_SERVICE_URL = "/service/yaahlan-trick/external/cp-love-chest-stage"
_METHOD = "getCpLoveChestHomepage"
_TEMPLATE_BODY = _REPO / "MOA-generative/templates/example-getCpLoveChestHomepage.body.json"


def _build_body(user_id: str, template: dict[str, Any]) -> dict[str, Any]:
    body = dict(template)
    body["userId"] = user_id
    body["uid"] = user_id
    body["_uid_"] = user_id
    body["localTime"] = int(time.time() * 1000)
    return body


def _summarize_love_value(business: dict[str, Any]) -> dict[str, Any]:
    data = business.get("data")
    if not isinstance(data, dict):
        return {"parsed": False, "raw": business}
    user_info = data.get("userInfo") if isinstance(data.get("userInfo"), dict) else {}
    cp_info = data.get("cpInfo") if isinstance(data.get("cpInfo"), dict) else {}
    return {
        "parsed": True,
        "currentLoveValue": data.get("currentLoveValue"),
        "claimedTierId": data.get("claimedTierId"),
        "countdownSec": data.get("countdownSec"),
        "userId": user_info.get("userId"),
        "userNickName": user_info.get("nickName"),
        "cpUserId": cp_info.get("userId"),
        "cpNickName": cp_info.get("nickName"),
        "note": "currentLoveValue 为 CP 双方共享周期爱意值，非各自独立字段",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="MOA 查询 CP 爱意宝箱主页（双方共享爱意值）")
    parser.add_argument("--user-id", required=True, help="查询方 userId（须已有 CP 关系）")
    parser.add_argument("--service-url", default=_SERVICE_URL, help="调用链 ServiceUrl（MSE 确认后可改）")
    parser.add_argument("--strict", type=int, default=1, choices=(0, 1), help="1=要求业务 ec=200")
    parser.add_argument("--timeout-ms", type=int, default=20000)
    args = parser.parse_args()

    template = json.loads(_TEMPLATE_BODY.read_text(encoding="utf-8"))
    body = _build_body(str(args.user_id).strip(), template)
    body_path = _REPO / ".tmp" / f"cp_love_chest_homepage_{args.user_id}.body.json"
    payload_path = _REPO / ".tmp" / f"cp_love_chest_homepage_{args.user_id}.payload.json"
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
        print(json.dumps({"ok": False, "error": "run_generative_moa 无 JSON 输出", "stderr": (proc.stderr or "")[-500:]}, ensure_ascii=False, indent=2))
        return 1

    summary = json.loads(stdout[stdout.find("{") :])
    business = summary.get("business") if isinstance(summary.get("business"), dict) else {}
    summary["loveValueSummary"] = _summarize_love_value(business)
    summary["bodyFile"] = str(body_path)
    summary["payloadFile"] = str(payload_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
