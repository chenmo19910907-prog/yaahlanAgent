#!/usr/bin/env python3
"""造数：仅好友可见动态（供 IT-MOM-REPOST-039）。

HTTP/MOA publishFeed 关键字段（Stage 抓包确认）:
  scope: "FRIEND"   # 空字符串为公开
  texts: '[{"text":"...","type":"1"}]'  # MOA 侧为 JSON 字符串

流程:
  1. mutual_follow_pair(测试账号, 作者) 互关
  2. publishFeed(scope=FRIEND, texts=...)

示例:
  python3 MOA/scripts/repost_friends_only_seed.py \\
    --author 100438156 --viewer 100261858 --text seed039xyz
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from moa.follow_relation import mutual_follow_pair


def main() -> int:
    parser = argparse.ArgumentParser(description="造仅好友可见原帖")
    parser.add_argument("--author", required=True, help="发帖 userId")
    parser.add_argument("--viewer", required=True, help="测试账号 userId（需与作者互关）")
    parser.add_argument("--text", default="seed039xyz", help="帖子正文")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    publish_body = {
        "appId": 2005,
        "area": "MENA",
        "lang": "en",
        "os": "android",
        "source": "discover",
        "userId": str(args.author),
        "scope": "FRIEND",
        "texts": json.dumps([{"text": args.text, "type": "1"}], ensure_ascii=False),
    }

    if args.dry_run:
        print("=== mutual_follow ===")
        print(json.dumps({"viewer": args.viewer, "author": args.author}, ensure_ascii=False))
        print("=== publishFeed ===")
        print(json.dumps({"serviceUri": "/service/feed/external/feed-stage", "method": "publishFeed", "args": [publish_body]}, ensure_ascii=False))
        return 0

    result = mutual_follow_pair(args.viewer, args.author, sleep_seconds=2.0)
    print(f"互关: ok={result.ok} forward={result.forward_em} reverse={result.reverse_em}", file=sys.stderr)
    if not result.ok:
        return 1

    print("请通过 yaahlan-mcp-stage queryMoaService_Stage 调用 publishFeed；参数见 --dry-run", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
