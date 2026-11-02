#!/usr/bin/env python3
"""变更挚友空间好友类型（buddyType）：发起申请 + 对方同意 + intimateHomePage 验收。

HTTP（Tunnel 实测 13311111111/13311111112）：
  applyChangeBuddyTypeInvitation — 发起方
  acceptChangeBuddyTypeInvitation — 接受方（body 须含与申请一致的 buddyType）
ServiceUrl: /service/yaahlan/user/intimate-api
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from project_api import repo_root, service_url  # noqa: E402

_REPO = repo_root()
_URL = service_url("intimateApiService", "/service/yaahlan/user/intimate-api")

_BUDDY_ALIASES: dict[str, str] = {
    "friend": "friend",
    "好友": "friend",
    "bestie": "bestie",
    "闺蜜": "bestie",
    "brother": "brother",
    "兄弟": "brother",
    "sister": "sister",
    "姐妹": "sister",
    "soulmate": "soulmate",
    "灵魂伴侣": "soulmate",
}

_SPACE_TITLE: dict[str, str] = {
    "friend": "Friend Space",
    "bestie": "Bestie Space",
    "brother": "Brother Space",
    "sister": "Sister Space",
    "soulmate": "Soulmate Space",
}


def normalize_buddy_type(raw: str) -> str:
    key = (raw or "").strip().lower()
    if key in _BUDDY_ALIASES:
        return _BUDDY_ALIASES[key]
    if raw.strip() in _BUDDY_ALIASES:
        return _BUDDY_ALIASES[raw.strip()]
    raise ValueError(
        f"未知 buddyType: {raw!r}；可选: friend, bestie, brother, sister, soulmate（或中文：姐妹、灵魂伴侣等）"
    )


def intimate_id_for(user_a: str, user_b: str) -> str:
    a, b = str(user_a).strip(), str(user_b).strip()
    if int(a) <= int(b):
        return f"{a}-{b}"
    return f"{b}-{a}"


def _write_body(path: Path, user_id: str, intimate_id: str, buddy_type: str, relationship_type: str) -> None:
    body = {
        "userId": user_id,
        "uid": user_id,
        "_uid_": user_id,
        "relationshipType": str(relationship_type),
        "intimateId": intimate_id,
        "buddyType": buddy_type,
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
        }
    summary["_returncode"] = proc.returncode
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="变更挚友好友类型 buddyType")
    parser.add_argument("--from-user", required=True, help="发起变更申请的一方 userId")
    parser.add_argument("--to-user", required=True, help="同意申请的一方 userId")
    parser.add_argument(
        "--buddy-type",
        required=True,
        help="目标类型：friend/bestie/brother/sister/soulmate 或 姐妹、灵魂伴侣 等",
    )
    parser.add_argument("--intimate-id", default="", help="intimateId；空则按两 userId 小-大自动生成")
    parser.add_argument("--relationship-type", default="2", help="默认 2=挚友/Friends")
    parser.add_argument("--timeout-ms", type=int, default=20000)
    parser.add_argument(
        "--workdir",
        default=str(_REPO / ".tmp" / "intimate_buddy_change"),
        help="中间 body/报告目录",
    )
    args = parser.parse_args()

    from_user = str(args.from_user).strip()
    to_user = str(args.to_user).strip()
    buddy_type = normalize_buddy_type(args.buddy_type)
    intimate_id = str(args.intimate_id).strip() or intimate_id_for(from_user, to_user)

    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    body_path = work / "body.json"
    report: dict[str, Any] = {
        "ok": False,
        "fromUser": from_user,
        "toUser": to_user,
        "buddyType": buddy_type,
        "intimateId": intimate_id,
        "relationshipType": str(args.relationship_type),
        "steps": {},
    }

    _write_body(body_path, from_user, intimate_id, buddy_type, args.relationship_type)
    apply = _run_generative(
        method="applyChangeBuddyTypeInvitation",
        body_path=body_path,
        out_path=work / "apply.json",
        timeout_ms=args.timeout_ms,
        strict=1,
    )
    biz_apply = apply.get("business") or {}
    report["steps"]["apply"] = {
        "ok": bool(apply.get("ok")),
        "ec": biz_apply.get("ec"),
        "em": biz_apply.get("em"),
        "error": apply.get("error"),
    }
    if not apply.get("ok"):
        report["error"] = apply.get("error") or f"发起失败 ec={biz_apply.get('ec')} em={biz_apply.get('em')}"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    _write_body(body_path, to_user, intimate_id, buddy_type, args.relationship_type)
    accept = _run_generative(
        method="acceptChangeBuddyTypeInvitation",
        body_path=body_path,
        out_path=work / "accept.json",
        timeout_ms=args.timeout_ms,
        strict=1,
    )
    biz_accept = accept.get("business") or {}
    report["steps"]["accept"] = {
        "ok": bool(accept.get("ok")),
        "ec": biz_accept.get("ec"),
        "em": biz_accept.get("em"),
        "error": accept.get("error"),
    }
    if not accept.get("ok"):
        report["error"] = accept.get("error") or f"同意失败 ec={biz_accept.get('ec')} em={biz_accept.get('em')}"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    home_body = {
        "userId": to_user,
        "uid": to_user,
        "relationshipType": str(args.relationship_type),
        "intimateId": intimate_id,
        "area": "MENA",
        "lang": "en",
        "appId": "2005",
        "osType": "android",
    }
    body_path.write_text(json.dumps(home_body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    home = _run_generative(
        method="intimateHomePage",
        body_path=body_path,
        out_path=work / "home.json",
        timeout_ms=args.timeout_ms,
        strict=0,
    )
    biz_home = home.get("business") or {}
    data = biz_home.get("data") if isinstance(biz_home.get("data"), dict) else {}
    space_title = data.get("spaceTitle")
    expected = _SPACE_TITLE.get(buddy_type, "")
    report["steps"]["homepage"] = {
        "ec": biz_home.get("ec"),
        "em": biz_home.get("em"),
        "spaceTitle": space_title,
        "expectedSpaceTitle": expected,
    }
    if biz_home.get("ec") not in (0, 200):
        report["error"] = f"主页验收失败: ec={biz_home.get('ec')} em={biz_home.get('em')}"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    if expected and space_title != expected:
        report["error"] = f"spaceTitle 不符: 期望 {expected!r} 实际 {space_title!r}"
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
