"""Log CLI。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any

from .env import load_local_env
from .kibana_discover import (
    KibanaDiscoverError,
    TZ8,
    bsearch,
    day_range_utc8,
    format_ts_beijing,
    hours_range_utc8,
)


def _parse_phrases(raw: list[str] | None) -> list[str]:
    phrases: list[str] = []
    for item in raw or []:
        for part in item.split(","):
            part = part.strip()
            if part:
                phrases.append(part)
    return phrases


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Yaahlan Kibana Discover 日志搜索（internal/bsearch，与 Discover 短语 AND 等价）"
    )
    parser.add_argument(
        "--phrase",
        action="append",
        dest="phrases",
        metavar="TEXT",
        help="搜索短语（可多次；多个短语为 AND）；逗号可一次传多个",
    )
    parser.add_argument("--index", default=None, help="ES 索引，默认 yaahlan-log*")
    parser.add_argument("--size", type=int, default=20, help="返回条数（Discover 单页最大 500）")
    parser.add_argument("--hours", type=float, help="最近 N 小时（东八区 now 为终点）")
    parser.add_argument(
        "--today",
        action="store_true",
        help="东八区当日 00:00–23:59（默认未指定 --hours 时使用）",
    )
    parser.add_argument("--cookie", default=os.environ.get("KIBANA_COOKIE"), help="可选 Cookie")
    parser.add_argument(
        "--output",
        choices=("table", "json"),
        default="table",
        help="输出格式",
    )
    parser.add_argument(
        "--count-only",
        action="store_true",
        help="仅输出命中总数（size=0）",
    )
    return parser


def _resolve_range(args: argparse.Namespace) -> tuple[str, str]:
    if args.hours is not None:
        return hours_range_utc8(float(args.hours))
    if args.today or args.hours is None:
        return day_range_utc8(datetime.now(TZ8))
    return day_range_utc8(datetime.now(TZ8))


def run(argv: list[str] | None = None) -> int:
    load_local_env()
    parser = build_parser()
    args = parser.parse_args(argv)
    phrases = _parse_phrases(args.phrases)
    if not phrases:
        print("error: 至少提供一个 --phrase", file=sys.stderr)
        return 1
    gte, lte = _resolve_range(args)
    size = 0 if args.count_only else max(1, min(int(args.size), 500))
    track_total = True
    try:
        total, hits = bsearch(
            phrases=phrases,
            gte=gte,
            lte=lte,
            index=args.index,
            size=size,
            track_total=track_total,
            cookie=(args.cookie or "").strip() or None,
        )
    except KibanaDiscoverError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 1

    if args.output == "json":
        payload: dict[str, Any] = {
            "total": total,
            "returned": len(hits),
            "phrases": phrases,
            "range": {"gte": gte, "lte": lte},
            "hits": [
                {
                    "timeBeijing": format_ts_beijing(h.timestamp_utc),
                    "service": h.service,
                    "host": h.host,
                    "line": h.line,
                }
                for h in hits
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"命中: {total if total is not None else '?'}  本页: {len(hits)}  条件: {' AND '.join(repr(p) for p in phrases)}")
    if args.count_only:
        return 0
    for h in hits:
        ts = format_ts_beijing(h.timestamp_utc)
        svc = h.service or "?"
        preview = h.line.replace("\n", " ")
        if len(preview) > 240:
            preview = preview[:240] + "…"
        print(f"\n[{ts}] {svc}\n{preview}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
