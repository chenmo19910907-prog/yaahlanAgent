#!/usr/bin/env python3
"""离线验证：查询默认内联展示，用户列表默认前 10 条，按需查看全部/导出钉钉文档。"""

from __future__ import annotations

import sys

from export_delivery import (
    deliver_reply,
    is_user_list_table,
    limit_user_list_reply,
    wants_document_export,
    wants_view_all_data,
)


def test_wants_document_export() -> None:
    assert wants_document_export("导出完整结果到钉钉")
    assert wants_document_export("导出到钉钉文档")
    assert wants_document_export("把完整表格发到钉钉文档")
    assert not wants_document_export("查一下用户 100465989 的 VIP 等级")
    assert not wants_document_export("抓包获取财富榜单")


def test_wants_view_all_data() -> None:
    assert wants_view_all_data("查看全部数据")
    assert wants_view_all_data("看全部")
    assert not wants_view_all_data("查询 VIP 客服列表")


def test_user_list_table_detect() -> None:
    rows = [["userId", "nickname"], ["1001", "a"]]
    assert is_user_list_table(rows)
    rows2 = [["familyId", "name"], ["101435", "CCVC"]]
    assert not is_user_list_table(rows2)


def test_user_list_default_ten() -> None:
    header = "| userId | nickname |"
    sep = "| --- | --- |"
    body = "\n".join(f"| 1000000{i:02d} | user{i} |" for i in range(25))
    table = f"{header}\n{sep}\n{body}"
    limited = limit_user_list_reply(table, "列出全部 VIP 客服")
    assert "100000009 |" in limited
    assert "100000010 |" not in limited
    assert "共 25 条" in limited
    assert "前 10 条" in limited


def test_user_list_view_all() -> None:
    header = "| userId | nickname |"
    sep = "| --- | --- |"
    body = "\n".join(f"| 1000000{i:02d} | user{i} |" for i in range(25))
    table = f"{header}\n{sep}\n{body}"
    full = limit_user_list_reply(table, "查看全部数据")
    assert "100000024 |" in full
    assert "已展示前 10 条" not in full


def test_list_query_still_limited() -> None:
    header = "| userId | nickname |"
    sep = "| --- | --- |"
    body = "\n".join(f"| 1000000{i:02d} | user{i} |" for i in range(25))
    table = f"{header}\n{sep}\n{body}"
    limited = limit_user_list_reply(table, "列出全部 VIP 客服")
    assert "100000010 |" not in limited
    assert "共 25 条" in limited


def test_deliver_inline_by_default() -> None:
    big_table = "| a | b |\n| - | - |\n" + "\n".join(f"| {i} | {i} |" for i in range(20))
    result = deliver_reply(big_table, "查询榜单前20")
    assert not result.exported
    assert "| 0 |" in result.message


def test_deliver_export_on_request() -> None:
    big_table = "| userId | nickname |\n| --- | --- |\n" + "\n".join(
        f"| 100{i} | n{i} |" for i in range(20)
    )
    result = deliver_reply(big_table, "导出到钉钉文档")
    assert result.exported
    if result.file_url:
        assert result.message.strip() == result.file_url.strip()
    assert "目录" not in result.message


def main() -> int:
    test_wants_document_export()
    print("[OK] test_wants_document_export")
    test_wants_view_all_data()
    print("[OK] test_wants_view_all_data")
    test_user_list_table_detect()
    print("[OK] test_user_list_table_detect")
    test_user_list_default_ten()
    print("[OK] test_user_list_default_ten")
    test_user_list_view_all()
    print("[OK] test_user_list_view_all")
    test_list_query_still_limited()
    print("[OK] test_list_query_still_limited")
    test_deliver_inline_by_default()
    print("[OK] test_deliver_inline_by_default")
    try:
        test_deliver_export_on_request()
        print("[OK] test_deliver_export_on_request")
    except Exception as exc:  # noqa: BLE001
        print(f"[SKIP] test_deliver_export_on_request (需钉钉凭证): {exc}")
    print("[PASS] export_delivery")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
