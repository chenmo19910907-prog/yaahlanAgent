#!/usr/bin/env python3
"""Form intimate pair (挚友/CP): Gift invite + MOA accept.

Flow:
  1) optional intimateDismiss (both id orders)
  2) Gift --intimate-invite (from -> to)
  3) resolve pending intimateId via intimateInvitationInfo (status=1)
  4) acceptIntimateInvitation as to-user
  5) intimateHomePage verify

relationshipType: 2=挚友（默认 gift 2005007129），1=CP（默认 gift 2005004592）
ServiceUrl: /service/yaahlan/user/intimate-api
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
_URL = "/service/yaahlan/user/intimate-api"
_DEFAULT_BUDDY_GIFT = "2005007129"  # buddyGiftList 特价礼（已抓包验证）
_DEFAULT_CP_GIFT = "2005004592"  # cpGiftList Neon Heart 1500钻（13311111112 抓包 intimateInvitePreviewPage）


def _default_gift_for_relationship(relationship_type: str) -> str:
    return _DEFAULT_CP_GIFT if str(relationship_type) == "1" else _DEFAULT_BUDDY_GIFT


def _write_body(path: Path, user_id: str, intimate_id: str, relationship_type: str) -> None:
    body = {
        "userId": user_id,
        "uid": user_id,
        "_uid_": user_id,
        "relationshipType": str(relationship_type),
        "intimateId": intimate_id,
        "area": "MENA",
        "lang": "en",
        "appId": "2005",
        "osType": "ios",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def _gift_invite(*, sender: str, receiver: str, gift_id: str) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "python3",
            str(_REPO / "Gift" / "gift_execute.py"),
            "--scene",
            "private",
            "--sender",
            sender,
            "--receivers",
            receiver,
            "--gift-id",
            gift_id,
            "--num",
            "1",
            "--intimate-invite",
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    data = _safe_json_loads(proc.stdout or "")
    if not data:
        return {
            "ok": False,
            "error": "gift_execute 无 JSON 输出",
            "returncode": proc.returncode,
            "stderrTail": (proc.stderr or "")[-400:],
            "stdoutTail": (proc.stdout or "")[-400:],
        }
    data["_returncode"] = proc.returncode
    return data


def _id_candidates(from_user: str, to_user: str) -> list[str]:
    # 邀请 pending 时常见 from-to；主页落库常见小-大
    a = f"{from_user}-{to_user}"
    b = f"{to_user}-{from_user}"
    return [a, b] if a != b else [a]


def main() -> int:
    parser = argparse.ArgumentParser(description="结挚友：Gift 发起 + MOA 同意")
    parser.add_argument("--from-user", required=True, help="发起方 userId")
    parser.add_argument("--to-user", required=True, help="接受方 userId")
    parser.add_argument(
        "--relationship-type",
        default="2",
        help="亲密类型：2=挚友（默认），1=CP（礼物须换 cpGiftList）",
    )
    parser.add_argument(
        "--gift-id",
        default="",
        help="申请礼物 giftId；空则按 relationshipType 选默认（挚友 2005007129 / CP 2005004592）",
    )
    parser.add_argument(
        "--dismiss-first",
        type=int,
        default=1,
        choices=(0, 1),
        help="1=先尝试解除已有关系（默认）；0=不解除",
    )
    parser.add_argument("--timeout-ms", type=int, default=20000)
    parser.add_argument(
        "--workdir",
        default=str(_REPO / ".tmp" / "intimate_form"),
        help="中间 body/报告目录",
    )
    args = parser.parse_args()

    from_user = str(args.from_user).strip()
    to_user = str(args.to_user).strip()
    gift_id = str(args.gift_id).strip() or _default_gift_for_relationship(args.relationship_type)
    if not from_user or not to_user:
        print(json.dumps({"ok": False, "error": "from/to user 不能为空"}, ensure_ascii=False))
        return 2
    if from_user == to_user:
        print(json.dumps({"ok": False, "error": "from/to 不能相同"}, ensure_ascii=False))
        return 2

    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    body_path = work / "body.json"
    report: dict[str, Any] = {
        "ok": False,
        "fromUser": from_user,
        "toUser": to_user,
        "relationshipType": str(args.relationship_type),
        "giftId": gift_id,
        "dismissFirst": bool(args.dismiss_first),
        "steps": {},
    }

    ids = _id_candidates(from_user, to_user)

    if args.dismiss_first:
        dismiss_rows: list[dict[str, Any]] = []
        for uid in (from_user, to_user):
            for iid in ids:
                _write_body(body_path, uid, iid, args.relationship_type)
                summary = _run_generative(
                    method="intimateDismiss",
                    body_path=body_path,
                    out_path=work / f"dismiss_{uid}_{iid}.json",
                    timeout_ms=args.timeout_ms,
                    strict=0,
                )
                biz = summary.get("business") or {}
                dismiss_rows.append(
                    {
                        "userId": uid,
                        "intimateId": iid,
                        "ec": biz.get("ec"),
                        "em": biz.get("em"),
                        "data": biz.get("data"),
                    }
                )
        report["steps"]["dismiss"] = dismiss_rows

    gift = _gift_invite(sender=from_user, receiver=to_user, gift_id=gift_id)
    report["steps"]["giftInvite"] = {
        "ok": bool(gift.get("ok")),
        "ec": (gift.get("response") or {}).get("ec") if isinstance(gift.get("response"), dict) else None,
        "em": (gift.get("response") or {}).get("em") if isinstance(gift.get("response"), dict) else None,
        "error": gift.get("error"),
        "response": gift.get("response"),
    }
    if not gift.get("ok"):
        report["error"] = gift.get("error") or "Gift 发起失败"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    time.sleep(1)

    pending_id: str | None = None
    info_rows: list[dict[str, Any]] = []
    for iid in ids:
        _write_body(body_path, to_user, iid, args.relationship_type)
        summary = _run_generative(
            method="intimateInvitationInfo",
            body_path=body_path,
            out_path=work / f"info_{iid}.json",
            timeout_ms=args.timeout_ms,
            strict=0,
        )
        biz = summary.get("business") or {}
        data = biz.get("data") if isinstance(biz.get("data"), dict) else {}
        row = {
            "intimateId": iid,
            "ec": biz.get("ec"),
            "em": biz.get("em"),
            "status": data.get("status"),
            "from": (data.get("fromInfo") or {}).get("userId"),
            "to": (data.get("toInfo") or {}).get("userId"),
        }
        info_rows.append(row)
        if str(data.get("status")) == "1" and not pending_id:
            pending_id = iid
    report["steps"]["invitationInfo"] = info_rows

    if not pending_id:
        # 回退：发起方-接受方（与成功抓包一致）
        pending_id = f"{from_user}-{to_user}"
        report["steps"]["invitationInfoFallback"] = pending_id

    report["intimateId"] = pending_id
    _write_body(body_path, to_user, pending_id, args.relationship_type)

    accept = _run_generative(
        method="acceptIntimateInvitation",
        body_path=body_path,
        out_path=work / "accept.json",
        timeout_ms=args.timeout_ms,
        strict=1,
    )
    report["steps"]["accept"] = {
        "ok": bool(accept.get("ok")),
        "businessOk": accept.get("businessOk"),
        "business": accept.get("business"),
        "error": accept.get("error"),
    }
    if not accept.get("ok"):
        report["error"] = accept.get("error") or "MOA 同意失败"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    home = _run_generative(
        method="intimateHomePage",
        body_path=body_path,
        out_path=work / "home.json",
        timeout_ms=args.timeout_ms,
        strict=0,
    )
    biz = home.get("business") or {}
    data = biz.get("data") if isinstance(biz.get("data"), dict) else {}
    info = data.get("intimateInfo") if isinstance(data.get("intimateInfo"), dict) else {}
    report["steps"]["homepage"] = {
        "ec": biz.get("ec"),
        "em": biz.get("em"),
        "from": (data.get("fromInfo") or {}).get("userId"),
        "to": (data.get("toInfo") or {}).get("userId"),
        "level": info.get("level"),
        "intimateId": info.get("intimateId") or data.get("intimateId"),
    }
    if biz.get("ec") not in (0, 200):
        report["error"] = f"主页验收失败: ec={biz.get('ec')} em={biz.get('em')}"
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
