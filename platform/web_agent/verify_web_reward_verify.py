#!/usr/bin/env python3
"""web_reward_verify / format_snapshot_inventory 单测。"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "workflow" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from reward_verify import (  # noqa: E402
    format_snapshot_inventory,
    summarize_web_reward_round,
)


class FormatSnapshotInventoryTests(unittest.TestCase):
    def test_lists_all_categories(self) -> None:
        snap = {
            "userId": "100001",
            "tsBeijing": "2026-10-28 14:00:00",
            "diamond": 10,
            "goldCoin": 5,
            "backpackGifts": {
                "g1": {"name": "Rose", "remain": 2, "price": 1, "expire": 1999999999000},
            },
            "backpackProps": {
                "p1": {"name": "券A", "propType": "游戏券", "count": 3, "validDays": 7},
            },
            "propsByType": {
                "10043": {
                    "h1": {"propName": "框1", "expireTime": 1999999999000, "count": 1},
                },
            },
            "nameplates": {
                "1139": {"title": "铭牌X", "count": 1, "remainDays": 30},
            },
            "cpMedalItems": [{"medalName": "True Love", "count": 2, "obtainTimeLabel": "2026-01-01 00:00:00"}],
        }
        md = format_snapshot_inventory(snap, user_label="测试号")
        self.assertIn("Rose", md)
        self.assertIn("券A", md)
        self.assertIn("框1", md)
        self.assertIn("铭牌X", md)
        self.assertIn("True Love", md)
        self.assertIn("金币", md)

    def test_summarize_web_round_uses_increment_days(self) -> None:
        before = {"userId": "1", "ts": 1000, "goldCoin": 10}
        after = {"userId": "1", "ts": 2000, "goldCoin": 20}
        diff = {
            "userId": "1",
            "beforeTs": 1000,
            "afterTs": 2000,
            "diamond": {"before": 100, "after": 150, "delta": 50},
            "diamondHistoryNew": [
                {
                    "diamondDiff": 50.0,
                    "desc": "Lucky Wheel",
                    "createTime": 1_500_000,
                    "createTimeLabel": "t",
                },
                {
                    "diamondDiff": 5.0,
                    "desc": "old",
                    "createTime": 500_000,
                    "createTimeLabel": "old",
                },
            ],
            "props": [
                {
                    "propId": "p1",
                    "propName": "框",
                    "propTypeCode": "10043",
                    "status": "new",
                    "validityPeriod": 3,
                    "expireTimeAfter": "2099-01-01 00:00:00 +0800",
                    "issued": True,
                    "actualIssuedDays": 3.0,
                }
            ],
            "backpackGifts": [],
            "cpMedals": [],
            "nameplates": [],
        }
        summary = summarize_web_reward_round(diff, before, after, user_label="u", round_no=1)
        self.assertEqual(summary["goldDelta"], 10)
        self.assertEqual(len(summary["diamondHistory"]), 1)
        self.assertEqual(summary["props"][0]["incrementDays"], 3.0)
        self.assertIn("Lucky Wheel", summary["markdown"])


if __name__ == "__main__":
    unittest.main()
