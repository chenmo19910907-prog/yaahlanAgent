"""VIP MOA CLI：体验卡下发 / 清除 / 查询。"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any

from .device import AdbError
from .recorded_scripts import load_test_accounts
from .vip_grant import dispatch_vip_try

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MOA_EXECUTE = _REPO_ROOT / "MOA/moa_execute.py"
_VIP_EXP_TEMPLATE = _REPO_ROOT / "MOA/templates/VIP-增加经验值.json"
_VIP_DEL_TEMPLATE = _REPO_ROOT / "MOA/templates/VIP-清除信息.json"


def add_vip_subparsers(sub: argparse._SubParsersAction) -> None:
    p_vip = sub.add_parser("vip", help="MOA VIP 体验卡 / 查询（配合页面学习门控）")
    vip_sub = p_vip.add_subparsers(dest="vip_command", required=True)

    p_try = vip_sub.add_parser("try", help="下发 VIP 体验卡")
    p_try.add_argument("--user-id", help="userId；与 --account 二选一")
    p_try.add_argument("--account", default="familyLeader", help="testAccounts 键名")
    p_try.add_argument("--level", type=int, required=True, help="体验等级 1-10")
    p_try.add_argument(
        "--days",
        type=int,
        default=1,
        help="体验天数，默认 1（86400 秒/天）",
    )
    p_try.add_argument(
        "--clear-first",
        action="store_true",
        help="下发前先清除 VIP 信息（已有体验卡且 ec:10011 时用）",
    )

    p_query = vip_sub.add_parser("query", help="查询当前 VIP 等级/体验等级")
    p_query.add_argument("--user-id", help="userId；与 --account 二选一")
    p_query.add_argument("--account", default="familyLeader")

    p_clear = vip_sub.add_parser("clear", help="清除 VIP 信息")
    p_clear.add_argument("--user-id", help="userId；与 --account 二选一")
    p_clear.add_argument("--account", default="familyLeader")


def _resolve_user_id(*, user_id: str | None, account: str | None) -> str:
    if user_id and str(user_id).strip():
        return str(user_id).strip()
    key = str(account or "").strip()
    if not key:
        raise ValueError("须指定 --user-id 或 --account")
    acct = load_test_accounts().get(key)
    if not isinstance(acct, dict):
        raise ValueError(f"testAccounts 无键名: {key}")
    uid = str(acct.get("userId", "")).strip()
    if not uid:
        raise ValueError(f"testAccounts.{key} 缺少 userId")
    return uid


def _run_moa(template: Path, extra: list[str]) -> dict[str, Any]:
    if not _MOA_EXECUTE.is_file():
        raise AdbError(f"缺少 MOA 入口: {_MOA_EXECUTE}")
    if not template.is_file():
        raise AdbError(f"缺少 MOA 模板: {template}")
    import json

    cmd = ["python3", str(_MOA_EXECUTE), "--payload-file", str(template), *extra]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        timeout=25,
        check=False,
    )
    if proc.returncode != 0:
        raise AdbError((proc.stderr or proc.stdout or "MOA 失败")[-500:])
    return json.loads(proc.stdout)


def handle_vip_command(args: argparse.Namespace) -> dict[str, Any]:
    uid = _resolve_user_id(
        user_id=getattr(args, "user_id", None),
        account=getattr(args, "account", None),
    )

    if args.vip_command == "query":
        out = _run_moa(
            _VIP_EXP_TEMPLATE,
            ["--vip-user-id", uid, "--vip-query-current"],
        )
        return {"ok": True, "userId": uid, "vipInfo": out}

    if args.vip_command == "clear":
        out = _run_moa(_VIP_DEL_TEMPLATE, ["--vip-del-user-id", uid])
        return {"ok": True, "userId": uid, "cleared": out}

    if args.vip_command == "try":
        if args.clear_first:
            _run_moa(_VIP_DEL_TEMPLATE, ["--vip-del-user-id", uid])
        days = max(1, int(args.days))
        result = dispatch_vip_try(
            uid,
            int(args.level),
            duration_seconds=days * 86400,
        )
        return {"ok": bool(result.get("ok")), "userId": uid, "dispatch": result}

    raise ValueError(f"未知 vip 子命令: {args.vip_command}")
