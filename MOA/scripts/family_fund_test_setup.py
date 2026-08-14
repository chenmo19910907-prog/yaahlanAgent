#!/usr/bin/env python3
"""家族基金测试数据准备：清贡献 → 设档位 → 加贡献 →（可选）成员贡献 → 查询验收。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MOA_EXECUTE = REPO / "MOA" / "moa_execute.py"


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def run_moa(extra_args: list[str]) -> None:
    cmd = [sys.executable, str(MOA_EXECUTE), *extra_args]
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.returncode != 0:
        if proc.stderr.strip():
            print(proc.stderr.strip(), file=sys.stderr)
        raise SystemExit(proc.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="家族基金测试数据准备")
    parser.add_argument("--family-id", required=True)
    parser.add_argument("--fund-tier", choices=["A", "B", "C"], default="C")
    parser.add_argument("--contribution", type=int, default=0, help="家族基金贡献值增量")
    parser.add_argument("--week", default="", help="周期周一 YYYYMMDD；空=本周")
    parser.add_argument("--member-user-id", default="")
    parser.add_argument("--member-contrib", type=int, default=0)
    parser.add_argument(
        "--reward-diamonds",
        type=int,
        default=0,
        help=">0 时走一键返奖（清贡献+设档位+设贡献+查询）",
    )
    parser.add_argument(
        "--clear-last-week",
        default="0",
        help="1/true=额外清除上周贡献",
    )
    args = parser.parse_args()

    family_id = str(args.family_id).strip()
    if not family_id:
        print("family-id 不能为空", file=sys.stderr)
        return 1

    base = ["--family-id", family_id]
    week = str(args.week or "").strip()
    week_args = ["--family-fund-week", week] if week else []

    if args.reward_diamonds > 0:
        run_moa(
            base
            + week_args
            + [
                "--payload-file",
                "MOA/templates/家族-设置基金档位.json",
                "--family-fund-reward-diamonds",
                str(args.reward_diamonds),
            ]
        )
        return 0

    run_moa(
        base
        + [
            "--payload-file",
            "MOA/templates/家族-清除基金贡献值.json",
            "--family-fund-clear",
            "--family-fund-week-offset",
            "0",
        ]
    )
    if _truthy(args.clear_last_week):
        run_moa(
            base
            + [
                "--payload-file",
                "MOA/templates/家族-清除基金贡献值.json",
                "--family-fund-clear",
                "--family-fund-week-offset",
                "-1",
            ]
        )
    # 须先清旧缓存再设档位；设档后勿清缓存（否则会按上周贡献重算回 B/A）。
    run_moa(
        base
        + week_args
        + [
            "--payload-file",
            "MOA/templates/家族基金-清除档位缓存.json",
            "--family-fund-tier-cache-clear",
            "--family-fund-week-offset",
            "0",
        ]
    )
    run_moa(
        base
        + [
            "--payload-file",
            "MOA/templates/家族-设置基金档位.json",
            "--family-fund-tier",
            str(args.fund_tier).upper(),
        ]
    )
    if args.contribution > 0:
        run_moa(
            base
            + week_args
            + [
                "--payload-file",
                "MOA/templates/家族-增加基金贡献值.json",
                "--family-fund-contrib",
                str(args.contribution),
            ]
        )
    member_id = str(args.member_user_id or "").strip()
    if member_id and args.member_contrib > 0:
        run_moa(
            base
            + week_args
            + [
                "--payload-file",
                "MOA/templates/家族-成员增加基金贡献值.json",
                "--family-member-fund-user-id",
                member_id,
                "--family-member-fund-contrib",
                str(args.member_contrib),
            ]
        )
    run_moa(
        base
        + week_args
        + [
            "--payload-file",
            "MOA/templates/家族-增加基金贡献值.json",
            "--family-fund-contrib",
            "0",
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
