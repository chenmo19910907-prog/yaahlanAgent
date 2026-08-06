"""MOA 下发 VIP 体验卡（遇 VIP 门控时自动解锁查看）。"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from .device import AdbError
from .project_paths import moa_execute_path, moa_template, repo_root

_MOA_TEMPLATE = moa_template("VIP-下发体验卡.json")
_DEFAULT_DURATION_SECONDS = 86400


def dispatch_vip_try(
    user_id: str,
    level: int,
    *,
    duration_seconds: int = _DEFAULT_DURATION_SECONDS,
) -> dict[str, Any]:
    """下发 VIP 体验等级（dispatchTryVip），level 1-10。"""
    uid = str(user_id or "").strip()
    if not uid:
        raise ValueError("user_id 不能为空")
    if not 1 <= level <= 10:
        raise ValueError("level 必须在 1-10 之间")
    if duration_seconds <= 0:
        raise ValueError("duration_seconds 必须为正整数")

    execute = moa_execute_path()
    if not _MOA_TEMPLATE.is_file():
        raise AdbError(f"缺少 MOA 模板: {_MOA_TEMPLATE}")
    if not execute.is_file():
        raise AdbError(f"缺少 MOA 入口: {execute}")

    cmd = [
        "python3",
        str(execute),
        "--payload-file",
        str(_MOA_TEMPLATE),
        "--vip-try-user-id",
        uid,
        "--vip-try-level",
        str(level),
        "--vip-try-duration-seconds",
        str(duration_seconds),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(repo_root()),
            timeout=25,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AdbError(f"MOA dispatchTryVip 超时: {exc}") from exc

    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        raise AdbError(
            f"MOA dispatchTryVip 失败（exit={proc.returncode}）"
            + (f": {stderr[-500:]}" if stderr else "")
        )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AdbError(f"MOA 返回非 JSON: {proc.stdout[:300]}") from exc

    ok = _moa_business_ok(payload)
    inner = payload.get("result") or payload
    biz = inner.get("result") if isinstance(inner, dict) else None
    ec = biz.get("ec") if isinstance(biz, dict) else inner.get("ec") if isinstance(inner, dict) else None
    em = biz.get("em") if isinstance(biz, dict) else inner.get("em") if isinstance(inner, dict) else None
    return {
        "ok": ok,
        "userId": uid,
        "tryLevel": level,
        "durationSeconds": duration_seconds,
        "ec": ec,
        "em": em,
    }


def _moa_business_ok(payload: dict[str, Any]) -> bool:
    inner = payload.get("result") or payload
    if not isinstance(inner, dict):
        return False
    biz = inner.get("result")
    if isinstance(biz, dict):
        ec = biz.get("ec")
        if ec in (0, "0", 200, "200") and biz.get("success") is not False:
            return True
    ec = inner.get("ec")
    return ec in (0, "0", 200, "200")