#!/usr/bin/env python3
"""离线验证 quoted_reply。"""

from __future__ import annotations

import sys

from quoted_reply import (
    compose_quoted_markdown,
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
    test_quote_text_from_inbound()
    print("[OK] test_quote_text_from_inbound")
    test_markdown_title()
    print("[OK] test_markdown_title")
    print("[PASS] quoted_reply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
