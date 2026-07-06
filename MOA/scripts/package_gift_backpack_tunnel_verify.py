#!/usr/bin/env python3
"""背包礼物 Tunnel 验收：getGiftTabListV3 背包 Tab → package.remain。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from adb.adb.gift_panel_analyze import verify_backpack_gift_from_tunnel  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Tunnel 验收用户背包礼物（须已打开礼物面板）")
    parser.add_argument("--user-id", "--momoid", dest="user_id", required=True)
    parser.add_argument("--bid", "--base-product-id", dest="base_product_id", default="")
    parser.add_argument("--name", "--gift-name", dest="gift_name", default="")
    parser.add_argument("--expect-remain", type=int, default=None)
    parser.add_argument("--since", type=int, default=600)
    parser.add_argument("--g-appid", default="All")
    parser.add_argument("--g-env", default="alpha")
    args = parser.parse_args()

    bid = str(args.base_product_id or "").strip() or None
    name = str(args.gift_name or "").strip() or None
    if not bid and not name and args.expect_remain is None:
        print("请至少指定 --bid、--name 或 --expect-remain 之一", file=sys.stderr)
        return 2

    out = verify_backpack_gift_from_tunnel(
        momoid=str(args.user_id).strip(),
        base_product_id=bid,
        gift_name=name,
        expected_remain=args.expect_remain,
        since_seconds=max(1, int(args.since)),
        g_appid=str(args.g_appid),
        g_env=str(args.g_env),
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))

    if not out.get("tunnelFound"):
        print("未抓到 getGiftTabListV3：请先在 App 打开礼物面板（橙色礼物盒）", file=sys.stderr)
        return 3
    if args.expect_remain is not None:
        return 0 if out.get("verifyOk") else 3
    return 0 if out.get("matchedCount", 0) > 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
