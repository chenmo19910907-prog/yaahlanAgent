#!/usr/bin/env python3
"""规划 CP 爱意值增量对应的最少送礼次数（stdout JSON）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "Gift") not in sys.path:
    sys.path.insert(0, str(_REPO / "Gift"))

from gift.cp_love_plan import (  # noqa: E402
    DEFAULT_MAX_NUM_PER_SEND,
    plan_cp_love_gift,
)
from gift.send_stage import StageGiftError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="规划 CP 爱意值送礼（最少 HTTP 次数）")
    parser.add_argument("--delta", type=int, required=True, help="目标爱意值增量")
    parser.add_argument(
        "--max-num",
        type=int,
        default=DEFAULT_MAX_NUM_PER_SEND,
        help=f"单次 --num 上限，默认 {DEFAULT_MAX_NUM_PER_SEND}",
    )
    args = parser.parse_args()
    try:
        plan = plan_cp_love_gift(args.delta, max_num_per_send=args.max_num)
    except (StageGiftError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    out = {"ok": True, **plan.to_dict()}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
