#!/usr/bin/env python3
"""verify_cp_love_plan：选礼规划单元测试（不 POST 送礼）。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "Gift") not in sys.path:
    sys.path.insert(0, str(_REPO / "Gift"))

from gift.cp_love_plan import plan_cp_love_gift  # noqa: E402


def _fake_query(gift_id: str) -> dict:
    table = {
        "2005000233": {"productName": "Rose", "price": 1.0},
        "2005001776": {"productName": "roses", "price": 99.0},
        "2005004730": {"productName": "Golden Lion King(复制)", "price": 1.0},
    }
    if gift_id not in table:
        raise RuntimeError(f"missing {gift_id}")
    return table[gift_id]


def test_500k_single_send_with_rose() -> None:
    with patch("gift.cp_love_plan.query_gift", side_effect=_fake_query):
        plan = plan_cp_love_gift(500_000)
    assert plan.send_count == 1
    assert plan.gift_id == "2005000233"
    assert plan.product_name == "Rose"
    assert plan.batches[0].num == 500_000


def test_forbidden_gift_excluded() -> None:
    with patch("gift.cp_love_plan.query_gift", side_effect=_fake_query):
        with patch(
            "gift.cp_love_plan.load_cp_love_gift_config",
            return_value=type(
                "Cfg",
                (),
                {
                    "default_gift_id": "2005000233",
                    "candidate_gift_ids": ("2005004730", "2005001776", "2005000233"),
                    "forbidden_gift_ids": frozenset({"2005004730", "2005001776"}),
                },
            )(),
        ):
            plan = plan_cp_love_gift(500_000)
    assert plan.gift_id == "2005000233"


def test_large_delta_splits_by_max_num() -> None:
    with patch("gift.cp_love_plan.query_gift", side_effect=_fake_query):
        plan = plan_cp_love_gift(
            600_000, candidate_gift_ids=("2005000233",), max_num_per_send=500_000
        )
    assert plan.send_count == 2
    assert plan.batches[0].num == 500_000
    assert plan.batches[1].num == 100_000


def main() -> int:
    test_500k_single_send_with_rose()
    test_forbidden_gift_excluded()
    test_large_delta_splits_by_max_num()
    print("verify_cp_love_plan: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
