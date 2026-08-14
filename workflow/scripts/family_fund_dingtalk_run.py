#!/usr/bin/env python3
"""家族基金全流程 → 钉钉表格验收（参考 PK 提款机 / 家族 PK 落表方案）。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
GATEWAY = REPO / "platform/dingtalk_gateway"

if str(GATEWAY) not in sys.path:
    sys.path.insert(0, str(GATEWAY))


def _current_week_monday() -> str:
    now = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    monday = now.fromordinal(now.toordinal() - now.weekday())
    return monday.strftime("%Y-%m-%d")


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, check=False)


def step_create_workbook(week_monday: str) -> dict[str, Any]:
    proc = _run(
        [
            sys.executable,
            str(GATEWAY / "family_fund_create_workbook.py"),
            "--week-monday",
            week_monday,
        ]
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "新建钉钉表失败")[-800:])
    return json.loads(proc.stdout)


def step_sync_mse(workbook_url: str, week_monday: str) -> str:
    proc = _run(
        [
            sys.executable,
            str(GATEWAY / "family_fund_mse_sync_to_workbook.py"),
            workbook_url,
            "--mode",
            "rebuild",
            "--week-monday",
            week_monday,
        ]
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "MSE 同步失败")[-800:])
    return proc.stdout.strip()


def step_write_data(workbook_url: str, *, family_id: str, week_monday: str) -> dict[str, Any]:
    proc = _run(
        [
            sys.executable,
            str(GATEWAY / "family_fund_data_to_workbook.py"),
            workbook_url,
            "--family-id",
            family_id,
            "--week-monday",
            week_monday,
        ]
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "写入家族数据失败")[-800:])
    return json.loads(proc.stdout)


def step_dispatch_verify(
    workbook_url: str,
    *,
    week_monday: str,
    skip_settle: bool,
    dispatch_offset: int = 0,
    dispatch_extra: str = "",
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(GATEWAY / "family_fund_dispatch_verify_to_workbook.py"),
        workbook_url,
        "--week-monday",
        week_monday,
        "--dispatch-offset",
        str(dispatch_offset),
    ]
    if dispatch_extra:
        cmd.extend(["--dispatch-extra", dispatch_extra])
    if skip_settle:
        cmd.append("--skip-settle")
    proc = _run(cmd)
    if proc.returncode not in (0, 2):
        raise RuntimeError((proc.stderr or proc.stdout or "发钻验收失败")[-800:])
    summary = json.loads(proc.stdout)
    summary["exitCode"] = proc.returncode
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="家族基金钉钉验收全流程")
    parser.add_argument("--week-monday", default=_current_week_monday())
    parser.add_argument("--family-id", default="", help="家族 ID；留空则仅建表 + MSE 同步")
    parser.add_argument("--capture-user-id", default="100121433", help="Tunnel 抓包账号")
    parser.add_argument("--workbook-url", default="", help="已有钉钉表 URL；留空则新建")
    parser.add_argument("--only-setup", action="store_true", help="仅建表 + MSE 同步")
    parser.add_argument("--skip-dispatch", action="store_true", help="跳过结算发奖与查钻验收")
    parser.add_argument("--skip-settle", action="store_true", help="发钻验收时不调用结算 MOA")
    parser.add_argument(
        "--dispatch-offset",
        type=int,
        default=0,
        help="家族基金奖励下发周偏移（0=本周，-1=上周；dispatchFamilyFundRewardTask）",
    )
    parser.add_argument(
        "--dispatch-extra",
        default="",
        help="家族基金奖励下发参数2 string（默认空）",
    )
    parser.add_argument("--wait-capture-seconds", type=int, default=0, help=">0 时等待 Tunnel 抓包")
    args = parser.parse_args()

    week_monday = args.week_monday.strip()
    out: dict[str, Any] = {"weekMonday": week_monday, "steps": []}

    if args.workbook_url.strip():
        workbook_url = args.workbook_url.strip()
        out["workbookUrl"] = workbook_url
        out["steps"].append({"step": "use_existing_workbook", "workbookUrl": workbook_url})
    else:
        created = step_create_workbook(week_monday)
        workbook_url = created["workbookUrl"]
        out.update(created)
        out["steps"].append({"step": "create_workbook", "workbookUrl": workbook_url})

    synced = step_sync_mse(workbook_url, week_monday)
    out["steps"].append({"step": "mse_sync", "workbookUrl": synced})
    out["workbookUrl"] = synced

    if args.only_setup or not args.family_id.strip():
        out["message"] = (
            "已完成：新建钉钉表 + MSE familyFundConfig 落表。"
            "请提供 --family-id，并在抓包账号打开家族主页+基金贡献榜后重跑。"
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    family_id = args.family_id.strip()
    if args.wait_capture_seconds > 0:
        from family_fund_tunnel_capture import wait_for_family_fund_capture  # noqa: PLC0415

        captures = wait_for_family_fund_capture(
            momoid=args.capture_user_id.strip(),
            family_id=family_id,
            wait_seconds=args.wait_capture_seconds,
        )
        out["tunnelCaptures"] = len(captures)
        if captures:
            out["tunnelSampleUrl"] = captures[0].get("url")

    data_summary = step_write_data(workbook_url, family_id=family_id, week_monday=week_monday)
    out["steps"].append({"step": "family_data", **data_summary})
    out["sheetNames"] = ["参数表", "家族基金测试"]

    if args.skip_dispatch:
        out["message"] = "已完成数据落表与应发钻测算；已跳过发钻验收。"
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    verify = step_dispatch_verify(
        workbook_url,
        week_monday=week_monday,
        skip_settle=args.skip_settle,
        dispatch_offset=args.dispatch_offset,
        dispatch_extra=args.dispatch_extra.strip(),
    )
    out["steps"].append({"step": "dispatch_verify", **verify})
    out["sheetName"] = verify.get("sheetName", "家族基金测试")
    out["allPass"] = verify.get("allPass")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if verify.get("allPass") else 2


if __name__ == "__main__":
    raise SystemExit(main())
