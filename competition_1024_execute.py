#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-1024 方案 CLI。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_DEFAULT_TRAIN = (
    _ROOT
    / "platform/web_agent/data/uploads/501cf15a0bee4d12/2fd347e81e6c45bd.json"
)
_DEFAULT_DEV = (
    _ROOT
    / "platform/web_agent/data/uploads/501cf15a0bee4d12/fc6ccafa93bf49cd.json"
)
_OUT = _ROOT / "competition_1024/data"


def cmd_prepare(args: argparse.Namespace) -> int:
    from competition_1024.data_prep import prepare_from_files

    counts = prepare_from_files(Path(args.train), Path(args.dev), Path(args.out))
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    print(f"输出目录: {args.out}")
    return 0


def cmd_eval_heuristic(args: argparse.Namespace) -> int:
    from competition_1024.data_prep import iter_jsonl, pick_single_demand, transform_record
    from competition_1024.heuristic_parser import parse_broadcast

    path = Path(args.dev)
    total = match_point_car = empty_ok = 0
    for row in iter_jsonl(path):
        total += 1
        gold = transform_record(row)
        pred = parse_broadcast(row["text"])
        g_dem = gold["demands"]
        p_dem = pred["demands"]
        if not g_dem and not p_dem:
            empty_ok += 1
            match_point_car += 1
            continue
        if g_dem and p_dem:
            g0, p0 = g_dem[0], p_dem[0]
            if g0["point"] == p0["point"] and g0["car_type"] == p0["car_type"]:
                match_point_car += 1
    print(
        json.dumps(
            {
                "dev_rows": total,
                "point_car_match_vs_greedy_gold": match_point_car,
                "accuracy_pct": round(100.0 * match_point_car / total, 1) if total else 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_demo_parse(args: argparse.Namespace) -> int:
    from competition_1024.heuristic_parser import parse_broadcast

    print(json.dumps(parse_broadcast(args.text), ensure_ascii=False, indent=2))
    return 0


def cmd_race(args: argparse.Namespace) -> int:
    from competition_1024.race_client import run_one_shot

    print(json.dumps(run_one_shot(args.token, args.api_base), ensure_ascii=False, indent=2))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import os

    if args.model:
        os.environ["COMPETITION_1024_MODEL_PATH"] = args.model
    os.environ["PORT"] = str(args.port)
    from competition_1024.model_server import main as serve_main

    serve_main()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="2026-1024 O.O 风格工具链")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_prep = sub.add_parser("prepare", help="生成单需求训练集 + special_tokens.txt")
    p_prep.add_argument("--train", default=str(_DEFAULT_TRAIN))
    p_prep.add_argument("--dev", default=str(_DEFAULT_DEV))
    p_prep.add_argument("--out", default=str(_OUT))
    p_prep.set_defaults(func=cmd_prepare)

    p_eval = sub.add_parser("eval-heuristic", help="启发式在 dev 上与贪心金标对比")
    p_eval.add_argument("--dev", default=str(_DEFAULT_DEV))
    p_eval.set_defaults(func=cmd_eval_heuristic)

    p_demo = sub.add_parser("demo-parse", help="单条广播启发式解析")
    p_demo.add_argument("--text", required=True)
    p_demo.set_defaults(func=cmd_demo_parse)

    p_race = sub.add_parser("race", help="拉广播→parse→dispatch 一枪")
    p_race.add_argument("--token", default=None)
    p_race.add_argument("--api-base", default=None)
    p_race.set_defaults(func=cmd_race)

    p_srv = sub.add_parser("serve", help="本地模型 HTTP 服务")
    p_srv.add_argument("--port", type=int, default=8080)
    p_srv.add_argument("--model", default=None, help="HF 模型目录；缺省用启发式")
    p_srv.set_defaults(func=cmd_serve)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
