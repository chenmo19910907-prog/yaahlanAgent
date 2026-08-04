#!/usr/bin/env python3
"""big_rich 模块单元测试（无需 Admin 鉴权）。"""

from __future__ import annotations

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from admin.big_rich import (  # noqa: E402
    USER_TYPE_VIP,
    build_big_rich_url,
    build_page_list_body,
    build_user_detail_body,
    verify_search_hit,
    verify_sort_monotonic,
)


def test_build_url() -> None:
    url = build_big_rich_url("https://yaahlan-admin-alpha.wemomo.com", "page_list")
    assert url.endswith("/admin/big-rich/pageList"), url


def test_page_list_body() -> None:
    body = build_page_list_body(user_type=USER_TYPE_VIP, user_id="100385728", query_period_type="MONTH_SUMMARY")
    assert body["userType"] == 2
    assert body["userId"] == "100385728"
    assert body["queryPeriodType"] == 4
    assert isinstance(body["newStartDate"], int)
    assert isinstance(body["oldStartDate"], int)
    assert body["oldStartDate"] < body["newStartDate"]


def test_user_detail_body() -> None:
    body = build_user_detail_body("100385728", start_date="2026-07-01", end_date="2026-07-31")
    assert body == {"userId": "100385728", "startDate": "20260701", "endDate": "20260731"}


def test_sort_and_search() -> None:
    rows = [{"rechargeUsd": 100}, {"rechargeUsd": 50}, {"rechargeUsd": 10}]
    assert not verify_sort_monotonic(rows, "rechargeUsd", descending=True)
    assert verify_sort_monotonic(rows, "rechargeUsd", descending=False)
    assert verify_search_hit([{"userId": "1"}, {"userId": "2"}], "1")
    assert not verify_search_hit([{"userId": "100"}], "100")


def main() -> int:
    test_build_url()
    test_page_list_body()
    test_user_detail_body()
    test_sort_and_search()
    print("verify_big_rich: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
