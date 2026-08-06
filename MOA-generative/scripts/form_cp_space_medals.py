#!/usr/bin/env python3
"""查询 CP 空间 CP 勋章（intimateHomePage → cpMedalTab）：Tunnel 抓包 → MOA-generative 执行。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from project_api import load_body_template, repo_root, service_url  # noqa: E402

_REPO = repo_root()
_SERVICE_URL = service_url("intimateApiService", "/service/yaahlan/user/intimate-api")
_METHOD = "intimateHomePage"
_TEMPLATE_BODY = load_body_template("templates/example-intimateHomePage.body.json")
_CP_LOVE_CHEST_URL = service_url("cpLoveChestService", "/service/yaahlan-trick/external/cp-love-chest")


def _id_candidates(user_id: str, cp_user_id: str) -> list[str]:
    a = f"{user_id}-{cp_user_id}"
    b = f"{cp_user_id}-{user_id}"
    return [a, b] if a != b else [a]


def _build_body(user_id: str, intimate_id: str, relationship_type: str, template: dict[str, Any]) -> dict[str, Any]:
    body = dict(template)
    body["userId"] = user_id
    body["uid"] = user_id
    body["_uid_"] = user_id
    body["relationshipType"] = str(relationship_type)
    body["intimateId"] = intimate_id
    return body


def _run_generative(*, body_path: Path, payload_path: Path, strict: int, timeout_ms: int) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "python3",
            str(_REPO / "MOA-generative/scripts/run_generative_moa.py"),
            "--url",
            _SERVICE_URL,
            "--method",
            _METHOD,
            "--body-file",
            str(body_path),
            "--out",
            str(payload_path),
            "--timeout-ms",
            str(timeout_ms),
            "--strict",
            str(strict),
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = (proc.stdout or "").strip()
    if "{" not in stdout:
        return {
            "ok": False,
            "error": "run_generative_moa 无 JSON 输出",
            "stderr": (proc.stderr or "")[-500:],
        }
    return json.loads(stdout[stdout.find("{") :])


def _resolve_cp_user_id(user_id: str, timeout_ms: int) -> str | None:
    body_path = _REPO / ".tmp" / f"cp_love_chest_homepage_{user_id}.body.json"
    payload_path = _REPO / ".tmp" / f"cp_love_chest_homepage_{user_id}.payload.json"
    template = json.loads((_REPO / "MOA-generative/templates/example-getCpLoveChestHomepage.body.json").read_text(encoding="utf-8"))
    body = dict(template)
    body["userId"] = user_id
    body["uid"] = user_id
    body["_uid_"] = user_id
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    proc = subprocess.run(
        [
            "python3",
            str(_REPO / "MOA-generative/scripts/run_generative_moa.py"),
            "--url",
            _CP_LOVE_CHEST_URL,
            "--method",
            "getCpLoveChestHomepage",
            "--body-file",
            str(body_path),
            "--out",
            str(payload_path),
            "--timeout-ms",
            str(timeout_ms),
            "--strict",
            "0",
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = (proc.stdout or "").strip()
    if "{" not in stdout:
        return None
    summary = json.loads(stdout[stdout.find("{") :])
    business = summary.get("business") if isinstance(summary.get("business"), dict) else {}
    data = business.get("data") if isinstance(business.get("data"), dict) else {}
    cp_info = data.get("cpInfo") if isinstance(data.get("cpInfo"), dict) else {}
    cp_user_id = cp_info.get("userId")
    return str(cp_user_id).strip() if cp_user_id else None


def _format_obtain_time(ms: Any) -> str | None:
    try:
        ts = int(ms) / 1000
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%y:%m:%d")


def _summarize_cp_medals(business: dict[str, Any]) -> dict[str, Any]:
    data = business.get("data")
    if not isinstance(data, dict):
        return {"parsed": False, "raw": business}
    tab = data.get("cpMedalTab") if isinstance(data.get("cpMedalTab"), dict) else {}
    medals_raw = tab.get("list") if isinstance(tab.get("list"), list) else []
    from_info = data.get("fromInfo") if isinstance(data.get("fromInfo"), dict) else {}
    to_info = data.get("toInfo") if isinstance(data.get("toInfo"), dict) else {}
    intimate_info = data.get("intimateInfo") if isinstance(data.get("intimateInfo"), dict) else {}
    medals: list[dict[str, Any]] = []
    for item in medals_raw:
        if not isinstance(item, dict):
            continue
        medals.append(
            {
                "medalName": item.get("medalName"),
                "num": item.get("num"),
                "obtainTime": item.get("obtainTime"),
                "obtainDate": _format_obtain_time(item.get("obtainTime")),
                "imageUrl": item.get("imageUrl"),
                "dynamicImageUrl": item.get("dynamicImageUrl") or None,
            }
        )
    return {
        "parsed": True,
        "showTab": tab.get("showTab"),
        "medalCount": len(medals),
        "medals": medals,
        "fromUserId": from_info.get("userId"),
        "fromNickName": from_info.get("nickName"),
        "toUserId": to_info.get("userId"),
        "toNickName": to_info.get("nickName"),
        "intimateId": intimate_info.get("intimateId") or data.get("intimateId"),
        "note": "CP 空间页 intimateHomePage 返回 cpMedalTab.list，按首次获取时间倒序",
    }


def _query_user_id_by_phone(phone: str) -> str:
    proc = subprocess.run(
        [
            "python3",
            str(_REPO / "MOA/moa_execute.py"),
            "--payload-file",
            str(_REPO / "MOA/templates/用户-按手机号查userId.json"),
            "--query-user-by-phone",
            phone,
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = proc.stdout or ""
    if "{" not in stdout:
        raise ValueError(f"手机号查 userId 失败: {(proc.stderr or stdout)[-300:]}")
    data = json.loads(stdout[stdout.find("{") : stdout.rfind("}") + 1])
    user_id = data.get("userId") or data.get("data")
    if not user_id:
        raise ValueError(f"手机号 {phone} 未注册或无法解析 userId")
    return str(user_id).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="MOA 查询 CP 空间 CP 勋章列表（cpMedalTab）")
    parser.add_argument("--user-id", help="查询方 userId（须已有 CP 关系）")
    parser.add_argument("--phone", help="手机号（与 --user-id 二选一，默认 +86）")
    parser.add_argument("--cp-user-id", help="CP 对方 userId；省略时尝试 getCpLoveChestHomepage 解析")
    parser.add_argument("--intimate-id", help="intimateId；省略时由 userId+cpUserId 组合候选")
    parser.add_argument("--relationship-type", default="1", help="1=CP（默认），2=挚友")
    parser.add_argument("--strict", type=int, default=1, choices=(0, 1), help="1=要求业务 ec=200")
    parser.add_argument("--timeout-ms", type=int, default=20000)
    args = parser.parse_args()

    user_id = str(args.user_id).strip() if args.user_id else ""
    if not user_id and args.phone:
        user_id = _query_user_id_by_phone(str(args.phone).strip())
    if not user_id:
        print(json.dumps({"ok": False, "error": "必须提供 --user-id 或 --phone"}, ensure_ascii=False, indent=2))
        return 1

    intimate_id = str(args.intimate_id).strip() if args.intimate_id else ""
    cp_user_id = str(args.cp_user_id).strip() if args.cp_user_id else ""
    if not intimate_id:
        if not cp_user_id:
            cp_user_id = _resolve_cp_user_id(user_id, args.timeout_ms) or ""
        if not cp_user_id:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "无法解析 CP 对方 userId，请传 --cp-user-id 或 --intimate-id",
                        "userId": user_id,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1
        candidates = _id_candidates(user_id, cp_user_id)
    else:
        candidates = [intimate_id]

    template = json.loads(_TEMPLATE_BODY.read_text(encoding="utf-8"))
    last_summary: dict[str, Any] | None = None
    resolved_intimate_id = intimate_id or None

    for candidate in candidates:
        body = _build_body(user_id, candidate, args.relationship_type, template)
        body_path = _REPO / ".tmp" / f"cp_space_medals_{user_id}_{candidate}.body.json"
        payload_path = _REPO / ".tmp" / f"cp_space_medals_{user_id}_{candidate}.payload.json"
        body_path.parent.mkdir(parents=True, exist_ok=True)
        body_path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary = _run_generative(
            body_path=body_path,
            payload_path=payload_path,
            strict=args.strict,
            timeout_ms=args.timeout_ms,
        )
        last_summary = summary
        business = summary.get("business") if isinstance(summary.get("business"), dict) else {}
        if summary.get("ok") and business.get("ec") in (0, 200):
            resolved_intimate_id = candidate
            summary["cpMedalSummary"] = _summarize_cp_medals(business)
            summary["bodyFile"] = str(body_path)
            summary["payloadFile"] = str(payload_path)
            summary["resolvedIntimateId"] = candidate
            if cp_user_id:
                summary["cpUserId"] = cp_user_id
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0

    if last_summary is None:
        last_summary = {"ok": False, "error": "未执行 MOA"}
    business = last_summary.get("business") if isinstance(last_summary.get("business"), dict) else {}
    last_summary["cpMedalSummary"] = _summarize_cp_medals(business)
    print(json.dumps(last_summary, ensure_ascii=False, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
