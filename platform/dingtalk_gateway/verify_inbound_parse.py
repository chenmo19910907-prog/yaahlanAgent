#!/usr/bin/env python3
"""离线验证 inbound_message 解析（无需钉钉凭证）。"""

from __future__ import annotations

import sys

import dingtalk_stream

from inbound_message import parse_inbound_message


def _assert(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        raise AssertionError(f"{name}: {detail}")


def test_text_with_link() -> None:
    msg = dingtalk_stream.ChatbotMessage.from_dict(
        {
            "msgtype": "text",
            "text": {"content": "@机器人 请读这个 PRD https://alidocs.dingtalk.com/i/nodes/abc"},
        }
    )
    inbound = parse_inbound_message(msg)
    _assert("text", inbound.text.startswith("请读这个 PRD"))
    _assert("link", len(inbound.links) == 1)
    _assert("link url", "alidocs.dingtalk.com" in inbound.links[0])


def test_picture_only() -> None:
    msg = dingtalk_stream.ChatbotMessage.from_dict(
        {
            "msgtype": "picture",
            "content": {"downloadCode": "dc-picture-001"},
        }
    )
    inbound = parse_inbound_message(msg)
    _assert("picture code", inbound.image_download_codes == ["dc-picture-001"])
    _assert("default prompt", "附图" in inbound.prompt_text())


def test_rich_text_mixed() -> None:
    msg = dingtalk_stream.ChatbotMessage.from_dict(
        {
            "msgtype": "richText",
            "content": {
                "richText": [
                    {"text": "@机器人 看图"},
                    {"downloadCode": "dc-rich-001"},
                    {"text": " 文档 "},
                    {"href": "https://example.com/doc"},
                ]
            },
        }
    )
    inbound = parse_inbound_message(msg)
    _assert("rich text", inbound.text == "看图\n 文档")
    _assert("rich image", inbound.image_download_codes == ["dc-rich-001"])
    _assert("rich link", inbound.links == ["https://example.com/doc"])
    _assert("summary", inbound.summary_label() == "文字+1图+1链接")


def main() -> int:
    tests = [test_text_with_link, test_picture_only, test_rich_text_mixed]
    for test in tests:
        test()
        print(f"[OK] {test.__name__}")
    print("[PASS] inbound_message 解析验证通过")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(1)
