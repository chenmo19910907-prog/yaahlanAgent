#!/usr/bin/env python3
"""Quick-add room member: MOA apply (applicant) + agree (owner).

HTTP:
  POST /yaahlan/room/member/apply   → room-member-stage.apply
  POST /yaahlan/room/member/agree   → room-member-stage.agree

Verified on alpha/stage via MOA-generative (Tunnel agree 2026-07-15).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_URL = "/service/room/external/room-member-stage"


def _safe_json_loads(raw: str) -> dict[str, Any]:
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        cleaned = "".join(ch if ord(ch) >= 32 or ch in "\n\r\t" else " " for ch in raw)
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else {}


def _write_apply_body(path: Path, *, user_id: str, room_id: str) -> None:
    body = {
        "userId": user_id,
        "roomId": room_id,
        "lang": "en",
        "area": "MENA",
        "appId": "2005",
        "os": "android",
        "osType": "android",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_agree_body(path: Path, *, owner_id: str, room_id: str, remote_id: str) -> None:
    body = {
        "userId": owner_id,
        "roomId": room_id,
        "remoteId": remote_id,
        "lang": "en",
        "area": "MENA",
        "appId": "2005",
        "os": "android",
        "osType": "android",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_generative(
    *,
    method: str,
    body_path: Path,
    out_path: Path,
    timeout_ms: int,
    strict: int,
) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "python3",
            str(_REPO / "MOA-generative" / "scripts" / "run_generative_moa.py"),
            "--url",
            _URL,
            "--method",
            method,
            "--body-file",
            str(body_path),
            "--out",
            str(out_path),
            "--timeout-ms",
            str(timeout_ms),
            "--strict",
            str(strict),
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=max(60, timeout_ms // 1000 + 30),
        check=False,
    )
    summary = _safe_json_loads(proc.stdout or "")
    if not summary:
        summary = {
            "ok": False,
            "error": "run_generative_moa 无 JSON 输出",
            "returncode": proc.returncode,
            "stderrTail": (proc.stderr or "")[-400:],
            "stdoutTail": (proc.stdout or "")[-400:],
        }
    summary["_returncode"] = proc.returncode
    return summary


def _biz_ok(summary: dict[str, Any], *, allow_codes: tuple[int | str, ...]) -> bool:
    if not summary.get("ok"):
        return False
    biz = summary.get("business") or {}
    ec = biz.get("ec")
    return ec in allow_codes or biz.get("success") is True


def main() -> int:
    parser = argparse.ArgumentParser(description="快速添加房间成员：MOA apply + agree")
    parser.add_argument("--applicant-user", required=True, help="申请人 userId")
    parser.add_argument("--owner-user", required=True, help="房主 userId（同意方）")
    parser.add_argument("--room-id", required=True, help="房间 roomId")
    parser.add_argument("--timeout-ms", type=int, default=20000)
    parser.add_argument(
        "--workdir",
        default=str(_REPO / ".tmp" / "room_member_form"),
        help="中间 body/payload 目录",
    )
    args = parser.parse_args()

    applicant = str(args.applicant_user).strip()
    owner = str(args.owner_user).strip()
    room_id = str(args.room_id).strip()
    if not applicant or not owner or not room_id:
        print(json.dumps({"ok": False, "error": "applicant/owner/room-id 不能为空"}, ensure_ascii=False))
        return 2
    if applicant == owner:
        print(json.dumps({"ok": False, "error": "申请人与房主不能相同"}, ensure_ascii=False))
        return 2

    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    apply_body = work / "apply.body.json"
    agree_body = work / "agree.body.json"

    report: dict[str, Any] = {
        "ok": False,
        "applicantUser": applicant,
        "ownerUser": owner,
        "roomId": room_id,
        "serviceUrl": _URL,
        "steps": {},
    }

    _write_apply_body(apply_body, user_id=applicant, room_id=room_id)
    apply = _run_generative(
        method="apply",
        body_path=apply_body,
        out_path=work / "apply.payload.json",
        timeout_ms=args.timeout_ms,
        strict=1,
    )
    apply_biz = apply.get("business") or {}
    report["steps"]["apply"] = {
        "ok": bool(apply.get("ok")),
        "businessOk": apply.get("businessOk"),
        "ec": apply_biz.get("ec"),
        "em": apply_biz.get("em"),
        "payloadPath": str(work / "apply.payload.json"),
    }
    if not _biz_ok(apply, allow_codes=(200,)):
        report["error"] = apply.get("error") or f"apply 失败 ec={apply_biz.get('ec')} em={apply_biz.get('em')}"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    time.sleep(0.5)

    _write_agree_body(agree_body, owner_id=owner, room_id=room_id, remote_id=applicant)
    agree = _run_generative(
        method="agree",
        body_path=agree_body,
        out_path=work / "agree.payload.json",
        timeout_ms=args.timeout_ms,
        strict=0,
    )
    agree_biz = agree.get("business") or {}
    report["steps"]["agree"] = {
        "ok": bool(agree.get("ok")),
        "businessOk": agree.get("businessOk"),
        "ec": agree_biz.get("ec"),
        "em": agree_biz.get("em"),
        "payloadPath": str(work / "agree.payload.json"),
    }
    # 20210111 = 已是成员（重复同意），200 = 成功
    if not _biz_ok(agree, allow_codes=(200, 20210111)):
        report["error"] = agree.get("error") or f"agree 失败 ec={agree_biz.get('ec')} em={agree_biz.get('em')}"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    report["ok"] = True
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2) from exc
