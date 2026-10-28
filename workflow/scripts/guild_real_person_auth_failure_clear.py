#!/usr/bin/env python3
"""公会场景：清除真人认证失败（2003 人脸冲突等）。

三步 MOA（与 MOA 测试台常用操作一致）：
1. queryRealPersonRecord — 读最近失败 reason 中的冲突 userId
2. internalAuthDeletePerson — 清冲突账号认证信息
3. resetRelationPersonExpireTime — 将冲突账号认证设为已过期（已成功认证时 delete 可能不够）

循环处理 reason 直至为空，最后清理待认证用户自身状态。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
MOA = REPO / "MOA" / "moa_execute.py"
QUERY_TPL = REPO / "MOA/templates/实名认证-查询认证记录.json"
DELETE_TPL = REPO / "MOA/templates/实名认证-清除认证信息.json"
EXPIRE_TPL = REPO / "MOA/templates/实名认证-设置认证过期时间.json"

sys.path.insert(0, str(REPO / "MOA"))
from moa.id_auth import extract_latest_id_auth_reason_list  # noqa: E402


def _run_moa(template: Path, extra: list[str], *, timeout_ms: int = 60000) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(MOA),
        "--payload-file",
        str(template),
        "--timeout-ms",
        str(timeout_ms),
        "--no-auto-sync-registry",
        *extra,
    ]
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or f"moa 退出码 {proc.returncode}")
    out = proc.stdout.strip()
    if not out:
        raise RuntimeError("moa 无 stdout")
    return json.loads(out)


def _inner_result(resp: dict[str, Any]) -> Any:
    outer = resp.get("result")
    if isinstance(outer, dict) and "result" in outer:
        return outer.get("result")
    return outer


def _query_reason_user_ids(user_id: str) -> list[str]:
    resp = _run_moa(QUERY_TPL, ["--id-auth-user-id", user_id, "--id-auth-output", "json"])
    inner = _inner_result(resp)
    return extract_latest_id_auth_reason_list(inner)


def _delete_person(uid: str) -> dict[str, Any]:
    return _run_moa(DELETE_TPL, ["--id-auth-delete-user-id", uid], timeout_ms=30000)


def _reset_expire_past(uid: str) -> dict[str, Any]:
    return _run_moa(
        EXPIRE_TPL,
        ["--id-auth-reset-expire-user-id", uid, "--id-auth-expire-at", "2020-01-01"],
        timeout_ms=30000,
    )


def _clear_conflict_account(uid: str, *, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"userId": uid, "dryRun": True}
    delete_resp = _delete_person(uid)
    expire_resp = _reset_expire_past(uid)
    return {"userId": uid, "delete": delete_resp, "expire": expire_resp}


def main() -> int:
    parser = argparse.ArgumentParser(description="清除用户真人认证失败（人脸冲突 reason）")
    parser.add_argument("--user-id", required=True, help="待重新认证的用户 userId")
    parser.add_argument("--max-rounds", type=int, default=10, help="reason 循环上限")
    parser.add_argument("--dry-run", action="store_true", help="仅查询 reason，不写 MOA")
    parser.add_argument(
        "--skip-target-reset",
        action="store_true",
        help="不清理待认证用户自身认证信息（仅清冲突账号）",
    )
    args = parser.parse_args()
    user_id = str(args.user_id).strip()
    if not user_id:
        print("user-id 不能为空", file=sys.stderr)
        return 2

    log: dict[str, Any] = {"userId": user_id, "rounds": []}
    for round_idx in range(1, max(1, args.max_rounds) + 1):
        reason_ids = _query_reason_user_ids(user_id)
        round_entry: dict[str, Any] = {"round": round_idx, "reasonUserIds": reason_ids, "cleared": []}
        log["rounds"].append(round_entry)
        if not reason_ids:
            break
        for uid in reason_ids:
            if uid == user_id:
                continue
            round_entry["cleared"].append(_clear_conflict_account(uid, dry_run=args.dry_run))

    if not args.skip_target_reset and not args.dry_run:
        log["targetReset"] = {
            "delete": _delete_person(user_id),
            "expire": _reset_expire_past(user_id),
        }

    remaining = _query_reason_user_ids(user_id) if not args.dry_run else log["rounds"][-1]["reasonUserIds"]
    log["remainingReasonUserIds"] = remaining
    log["ok"] = not remaining
    print(json.dumps(log, ensure_ascii=False, indent=2))
    if remaining:
        print(f"仍有冲突账号未清干净: {remaining}", file=sys.stderr)
        return 4
    print("真人认证失败冲突已处理，请让用户重新发起认证。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
