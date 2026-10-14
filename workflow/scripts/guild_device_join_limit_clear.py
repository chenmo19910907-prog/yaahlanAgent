#!/usr/bin/env python3
"""按设备 mmuid/mmuidv3 查询曾加入公会账号并批量删除设备入会绑定（两步 MOA）。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
MOA = REPO / "MOA" / "moa_execute.py"
QUERY_TPL = REPO / "MOA/templates/公会-按设备查曾加入公会账号.json"
DELETE_TPL = REPO / "MOA/templates/公会-批量删除设备入会绑定.json"


def _run_moa(extra: list[str], *, timeout_ms: int = 60000) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(MOA),
        "--payload-file",
        extra[0],
        "--timeout-ms",
        str(timeout_ms),
        "--no-auto-sync-registry",
        *extra[1:],
    ]
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or f"moa 退出码 {proc.returncode}")
    out = proc.stdout.strip()
    if not out:
        raise RuntimeError("moa 无 stdout")
    data = json.loads(out)
    return data


def _extract_user_ids(resp: dict[str, Any]) -> list[str]:
    inner = resp.get("result")
    if isinstance(inner, dict):
        result = inner.get("result")
        if isinstance(result, list):
            return [str(x) for x in result if str(x).strip()]
    if isinstance(inner, list):
        return [str(x) for x in inner if str(x).strip()]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="清除设备「已存在已加入公会账号」绑定")
    parser.add_argument("--mmuidv3", required=True, help="设备 mmuid 或 mmuidv3")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅查询 userId 列表，不执行删除",
    )
    args = parser.parse_args()
    device = str(args.mmuidv3).strip()
    if not device:
        print("mmuidv3 不能为空", file=sys.stderr)
        return 2

    query_resp = _run_moa(
        [str(QUERY_TPL), "--guild-device-mmuidv3", device],
        timeout_ms=30000,
    )
    user_ids = _extract_user_ids(query_resp)
    print(json.dumps({"device": device, "userIds": user_ids}, ensure_ascii=False, indent=2))
    if not user_ids:
        print("该设备无曾加入公会成功的账号记录，无需删除。", file=sys.stderr)
        return 0
    if args.dry_run:
        print("dry-run：跳过 batchDelAnchorMmuidv3Record", file=sys.stderr)
        return 0

    ids_json = json.dumps(user_ids, ensure_ascii=False, separators=(",", ":"))
    del_resp = _run_moa(
        [str(DELETE_TPL), "--guild-anchor-user-ids-json", ids_json],
        timeout_ms=60000,
    )
    print(json.dumps({"delete": del_resp}, ensure_ascii=False, indent=2))
    inner = del_resp.get("result") if isinstance(del_resp.get("result"), dict) else {}
    if inner.get("ec") not in (0, None) and del_resp.get("ec") not in (0, 200):
        print("删除 MOA 返回异常", file=sys.stderr)
        return 4
    print("已提交删除设备入会绑定。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
