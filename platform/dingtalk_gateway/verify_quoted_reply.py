#!/usr/bin/env python3
"""离线验证 quoted_reply。"""

from __future__ import annotations

import sys

from quoted_reply import (
    compose_quoted_markdown,
    format_at_user_prefix,
    format_markdown_quote,
    markdown_title_from_quote,
    quote_text_from_inbound,
)
from inbound_message import InboundMessage


def test_format_markdown_quote_multiline() -> None:
    text = "查询13311111111的\n公会成员"
    quoted = format_markdown_quote(text)
    assert "> **提问**" in quoted
    assert "> 查询13311111111的" in quoted
    assert "> 公会成员" in quoted


def test_format_markdown_quote_truncates() -> None:
    long_text = "a" * 300
    quoted = format_markdown_quote(long_text, max_chars=20)
    assert "> **提问**" in quoted
    assert "…" in quoted


def test_compose_quoted_markdown() -> None:
    body = "| 手机号 | userId |\n| --- | --- |"
    out = compose_quoted_markdown(body, "查询公会成员", at_user_id="user123")
    assert out.startswith("@user123")
    assert "> **提问**" in out
    assert "> 查询公会成员" in out
    assert "---" in out
    assert "| 手机号 |" in out


def test_compose_quoted_markdown_uses_staff_id_for_at() -> None:
    body = "结果"
    out = compose_quoted_markdown(
        body,
        "测试",
        at_user_id="32274159141215328",
        at_user_name="陈墨",
    )
    assert out.startswith("@32274159141215328")


def test_format_at_user_prefix_with_avatar() -> None:
    url = "http://172.18.125.90:18766/api/dingtalk/avatar-inline/u1?v=1"
    out = format_at_user_prefix("陈墨", avatar_ref=url)
    assert f"![]({url})" in out
    assert " 陈墨" in out or out.endswith("陈墨\n\n")
    assert "@陈墨" not in out
    assert "{:height" not in out


def test_format_at_user_prefix_with_data_uri() -> None:
    data_uri = "data:image/jpeg;base64,/9j/4AAQ"
    out = format_at_user_prefix("陈墨", avatar_ref=data_uri)
    assert out.startswith(f"![]({data_uri})")
    assert " 陈墨" in out
    assert "@data:" not in out


def test_format_at_user_prefix_with_html_img() -> None:
    html = '<img src="https://cdn.example/a.png" width="32" height="32" />'
    out = format_at_user_prefix("陈墨", avatar_ref=html)
    assert out.startswith(html)
    assert " 陈墨" in out
    assert "@陈墨" not in out


def test_quote_text_from_inbound() -> None:
    inbound = InboundMessage(text="查看全部数据")
    assert quote_text_from_inbound(inbound) == "查看全部数据"
    assert quote_text_from_inbound(InboundMessage()) is None


def test_markdown_title() -> None:
    assert markdown_title_from_quote("查询13311111111的公会成员") == "查询13311111111的公会成员"
    assert markdown_title_from_quote("x" * 30).endswith("…")


def main() -> int:
    test_format_markdown_quote_multiline()
    print("[OK] test_format_markdown_quote_multiline")
    test_format_markdown_quote_truncates()
    print("[OK] test_format_markdown_quote_truncates")
    test_compose_quoted_markdown()
    print("[OK] test_compose_quoted_markdown")
    test_compose_quoted_markdown_uses_staff_id_for_at()
    print("[OK] test_compose_quoted_markdown_uses_staff_id_for_at")
    test_format_at_user_prefix_with_avatar()
    print("[OK] test_format_at_user_prefix_with_avatar")
    test_format_at_user_prefix_with_data_uri()
    print("[OK] test_format_at_user_prefix_with_data_uri")
    test_format_at_user_prefix_with_html_img()
    print("[OK] test_format_at_user_prefix_with_html_img")
    test_quote_text_from_inbound()
    print("[OK] test_quote_text_from_inbound")
    test_markdown_title()
    print("[OK] test_markdown_title")
    print("[PASS] quoted_reply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
