"""页面学习 CLI：scan / probe，与主 cli 解耦。"""

from __future__ import annotations

import argparse
from typing import Any

from .page_learn import run_probe, run_scan


def add_learn_subparsers(sub: argparse._SubParsersAction) -> None:
    p_learn = sub.add_parser(
        "learn",
        help="学习 App 各底栏帧入口（扫描 UI → 页面地图.json）",
    )
    learn_sub = p_learn.add_subparsers(dest="learn_command", required=True)

    p_scan = learn_sub.add_parser("scan", help="扫描可点入口（不点击）")
    p_scan.add_argument(
        "--tab",
        choices=["game", "room", "msg", "moment", "me", "all"],
        default="all",
    )
    p_scan.add_argument("--scroll-passes", type=int, default=6)

    p_probe = learn_sub.add_parser("probe", help="点击验收页面地图中的入口")
    p_probe.add_argument(
        "--tab",
        choices=["game", "room", "msg", "moment", "me", "all"],
        default="all",
    )
    p_probe.add_argument(
        "--account",
        default="familyLeader",
        help="VIP 门控时 MOA 下发体验卡的 testAccounts 键名",
    )
    p_probe.add_argument("--limit", type=int, default=20, help="最多探测条数")
    p_probe.add_argument(
        "--rescan",
        action="store_true",
        help="忽略已有页面地图，先重新 scan 再 probe",
    )
    p_probe.add_argument("--no-vip", action="store_true", help="遇 VIP 门控不 MOA 下发")


def handle_learn_command(args: argparse.Namespace, *, serial: str) -> dict[str, Any]:
    if args.learn_command == "scan":
        return run_scan(
            serial,
            tab=args.tab,
            scroll_passes=max(1, int(args.scroll_passes)),
        )
    if args.learn_command == "probe":
        return run_probe(
            serial,
            tab=args.tab,
            account=str(args.account),
            limit=max(1, int(args.limit)),
            auto_vip=not bool(args.no_vip),
            rescan=bool(args.rescan),
        )
    raise ValueError(f"未知 learn 子命令: {args.learn_command}")
