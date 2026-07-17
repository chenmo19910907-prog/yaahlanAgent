#!/usr/bin/env python3
"""markdown_display 单测。"""

from __future__ import annotations

from markdown_display import enhance_markdown_list_indent


def test_indent_lists_after_heading() -> None:
    raw = """### 步骤 3：收礼榜与档位
- 2026-07-11 收礼榜：大族 8 个
- 「家族PK档位」304 行

### 步骤 4：匹配验收
- 清除并重匹配
"""
    out = enhance_markdown_list_indent(raw)
    assert "  - 2026-07-11" in out
    assert "  - 清除并重匹配" in out
    assert out.count("\n- ") == 0


def test_preserve_existing_nested_indent() -> None:
    raw = """1. 结论
   - `.tmp/a.json`
   - `.tmp/b.json`
"""
    out = enhance_markdown_list_indent(raw)
    assert "   - `.tmp/a.json`" in out


def main() -> None:
    test_indent_lists_after_heading()
    print("[OK] test_indent_lists_after_heading")
    test_preserve_existing_nested_indent()
    print("[OK] test_preserve_existing_nested_indent")
    print("[PASS] markdown_display")


if __name__ == "__main__":
    main()
