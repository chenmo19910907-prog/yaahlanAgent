"""Tunnel CLI。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from .client import list_requests, normalize_request_list, tunnel_success
from .env import load_local_env, load_online_env
from .online_config import online_defaults
from .paths import tunnel_dir
from .summary import format_list_summary, format_request_detail


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tunnel 抓包平台本地查询")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("TUNNEL_BASE_URL", "https://tunnel.wemomo.com"),
        help="Tunnel 域名，默认 TUNNEL_BASE_URL",
    )
    parser.add_argument("--momoid", required=True, help="用户 userId（momoid）")
    parser.add_argument(
        "--start-time",
        type=int,
        help="起始 Unix 时间戳（秒）；与 --since 二选一，优先本参数",
    )
    parser.add_argument(
        "--since",
        type=int,
        default=3600,
        help="查询最近 N 秒内的请求（默认 3600；未指定 --start-time 时生效）",
    )
    parser.add_argument("--keyword", default="", help="URL/接口关键字过滤")
    parser.add_argument(
        "--g-appid",
        default=os.environ.get("TUNNEL_G_APPID", "All"),
        help="应用过滤，如 All / yaahlan / sc_dev_all",
    )
    parser.add_argument(
        "--g-env",
        default=os.environ.get("TUNNEL_G_ENV", "alpha"),
        help="环境过滤，如 alpha / overseas",
    )
    parser.add_argument(
        "--mode",
        default="tunnel",
        help="查询模式，默认 tunnel",
    )
    parser.add_argument(
        "--request-id",
        help="展示单条请求详情（_id）；仍会先拉列表再匹配",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="摘要模式最多展示条数",
    )
    parser.add_argument(
        "--output",
        choices=("summary", "json"),
        default="summary",
        help="输出格式",
    )
    parser.add_argument("--timeout-ms", type=int, default=15000, help="HTTP 超时（毫秒）")
    parser.add_argument(
        "--线上环境",
        dest="online_env",
        action="store_true",
        help="使用线上 Tunnel（g_env=overseas + .env.online.local）；仅当用户提示词含「线上环境」时由 Agent 调用",
    )
    return parser


def _apply_online_tunnel_args(args: argparse.Namespace, base_dir: str) -> None:
    load_online_env(base_dir)
    defaults = online_defaults()

    args.base_url = os.environ.get("TUNNEL_ONLINE_BASE_URL") or defaults.get("baseUrl") or args.base_url
    cookie = os.environ.get("TUNNEL_ONLINE_COOKIE", "").strip()
    if cookie:
        os.environ["TUNNEL_COOKIE"] = cookie

    if os.environ.get("TUNNEL_ONLINE_G_APPID"):
        args.g_appid = os.environ["TUNNEL_ONLINE_G_APPID"]
    elif defaults.get("gAppid"):
        args.g_appid = str(defaults["gAppid"])

    if os.environ.get("TUNNEL_ONLINE_G_ENV"):
        args.g_env = os.environ["TUNNEL_ONLINE_G_ENV"]
    elif defaults.get("gEnv"):
        args.g_env = str(defaults["gEnv"])

    if defaults.get("mode"):
        args.mode = str(defaults["mode"])

    referer = os.environ.get("TUNNEL_ONLINE_REFERER") or defaults.get("referer") or ""
    if referer:
        os.environ["TUNNEL_REFERER"] = referer
    user_agent = os.environ.get("TUNNEL_ONLINE_USER_AGENT", "").strip()
    if user_agent:
        os.environ["TUNNEL_USER_AGENT"] = user_agent


def main(argv: list[str] | None = None) -> int:
    base_dir = tunnel_dir()
    load_local_env(base_dir)
    args = build_parser().parse_args(argv)

    if getattr(args, "online_env", False):
        try:
            _apply_online_tunnel_args(args, base_dir)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2

    start_time = args.start_time if args.start_time is not None else int(time.time()) - args.since

    try:
        payload = list_requests(
            base_url=args.base_url,
            momoid=args.momoid,
            start_time=start_time,
            keyword=args.keyword,
            g_appid=args.g_appid,
            g_env=args.g_env,
            mode=args.mode,
            timeout_s=args.timeout_ms / 1000.0,
        )
    except (ValueError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if not tunnel_success(payload.get("ec")):
        print(
            f"ERROR: Tunnel ec={payload.get('ec')} em={payload.get('em')}",
            file=sys.stderr,
        )
        if args.output == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    items = normalize_request_list(payload)

    if args.request_id:
        matched = next((x for x in items if x.get("_id") == args.request_id), None)
        if matched is None:
            print(f"ERROR: 未找到 _id={args.request_id}", file=sys.stderr)
            return 1
        if args.output == "json":
            print(json.dumps(matched, ensure_ascii=False, indent=2))
        else:
            print(format_request_detail(matched))
        return 0

    if args.output == "json":
        print(json.dumps({"meta": payload.get("data"), "items": items}, ensure_ascii=False, indent=2))
        return 0

    print(format_list_summary(items, limit=args.limit))
    return 0
