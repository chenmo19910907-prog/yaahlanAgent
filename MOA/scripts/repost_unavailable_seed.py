#!/usr/bin/env python3
"""造数：原帖删除后的不可见转发帖（供 IT-MOM-REPOST-043~046）。

流程:
  1. publishFeed(originalFeedId=...) 由 repostUser 转发
  2. deleteFeed 删除原作者原帖

依赖 yaahlan-mcp-stage queryMoaService_Stage；也可手工在 MSE 调用 feed-stage。

示例:
  python3 MOA/scripts/repost_unavailable_seed.py \\
    --repost-user 100261858 \\
    --original-feed 7070612_100461128 \\
    --original-user 100461128
"""

from __future__ import annotations

import argparse
import json
import sys

FEED_STAGE = "/service/feed/external/feed-stage"


def call_moa(method: str, body: dict) -> dict:
    """通过 Cursor MCP 不可用时的占位：打印待调用参数，供 Agent/人工执行。"""
    print(json.dumps({"serviceUri": FEED_STAGE, "method": method, "args": [body]}, ensure_ascii=False))
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="造不可见原帖的转发帖")
    parser.add_argument("--repost-user", required=True, help="转发者 userId")
    parser.add_argument("--original-feed", required=True, help="被转发原帖 feedId")
    parser.add_argument("--original-user", required=True, help="原帖作者 userId")
    parser.add_argument("--dry-run", action="store_true", help="仅打印 MOA 参数")
    args = parser.parse_args()

    repost_body = {
        "appId": 2005,
        "area": "MENA",
        "lang": "en",
        "os": "android",
        "source": "discover",
        "userId": str(args.repost_user),
        "originalFeedId": str(args.original_feed),
    }
    delete_body = {
        "feedId": str(args.original_feed),
        "userId": str(args.original_user),
    }

    if args.dry_run:
        print("=== publishFeed (repost) ===")
        call_moa("publishFeed", repost_body)
        print("=== deleteFeed (original) ===")
        call_moa("deleteFeed", delete_body)
        return 0

    print(
        "请通过 yaahlan-mcp-stage queryMoaService_Stage 依次调用上述两个方法；"
        "本脚本默认 --dry-run 输出参数。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
