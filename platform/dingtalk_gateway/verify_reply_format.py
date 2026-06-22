#!/usr/bin/env python3
"""离线验证 reply_formatter。"""

from __future__ import annotations

import sys

from reply_formatter import format_group_reply

HTML_FAIL = "执行失败: 返回不是合法 JSON: <!doctype html><title>Aegis SSO_MSE管理平台</title>"


def test_vip_cookie_expired() -> None:
    msg = format_group_reply(HTML_FAIL, prompt="100465989升级 VIP3", source="route")
    assert "MOA 测试环境登录已过期" in msg
    assert "<!doctype" not in msg.lower()
    assert "100465989" in msg


def test_vip_success_json() -> None:
    raw = '{"ec": 0, "em": "ok", "result": {"ec": 0, "em": "success"}}'
    msg = format_group_reply(raw, prompt="100465989升级 VIP3", source="route")
    assert "成功" in msg
    assert "100465989" in msg


def main() -> int:
    test_vip_cookie_expired()
    print("[OK] test_vip_cookie_expired")
    test_vip_success_json()
    print("[OK] test_vip_success_json")
    print("[PASS] reply_formatter")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
