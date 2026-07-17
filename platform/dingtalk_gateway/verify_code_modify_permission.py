#!/usr/bin/env python3
"""离线验证 code_modify_permission。"""

from __future__ import annotations

import sys

from code_modify_permission import (
    allow_moa_registry_in_readonly,
    is_code_modify_allowed,
    load_code_modify_allowlist,
    looks_like_code_modify_request,
)


def test_allowlist_owner() -> None:
    cfg = load_code_modify_allowlist()
    assert "32274159141215328" in cfg.allowed_staff_ids
    assert is_code_modify_allowed(
        sender_staff_id="32274159141215328",
        sender_id="ignored",
    )


def test_deny_unknown_user() -> None:
    assert not is_code_modify_allowed(
        sender_staff_id="99999999999999999",
        sender_id="unknown",
    )


def test_code_modify_intent() -> None:
    assert looks_like_code_modify_request("增加一个权限能力，只有我能改 cursor 代码逻辑")
    assert looks_like_code_modify_request("修改 dingtalk_gateway/server.py")
    assert looks_like_code_modify_request("给 gateway 加上引用回复能力")


def test_not_code_modify_ops() -> None:
    assert not looks_like_code_modify_request("查询13311111111的用户信息")
    assert not looks_like_code_modify_request("100465989升级 VIP3")
    assert not looks_like_code_modify_request("当前的Vip客服有哪些")
    assert not looks_like_code_modify_request("导出到钉钉文档")


def test_moa_registry_open_to_all() -> None:
    assert not looks_like_code_modify_request("帮我把MOA入库")
    assert not looks_like_code_modify_request(
        "这是根据家族 id 获取所有家族成员 id 的 MOA，帮我入库"
    )
    assert not looks_like_code_modify_request("查询收礼日榜的MOA，limit最多可以填入500，入库")


def test_allow_moa_registry_in_readonly() -> None:
    assert allow_moa_registry_in_readonly(code_modify_allowed=False)
    assert not allow_moa_registry_in_readonly(code_modify_allowed=True)


def main() -> int:
    test_allowlist_owner()
    print("[OK] test_allowlist_owner")
    test_deny_unknown_user()
    print("[OK] test_deny_unknown_user")
    test_code_modify_intent()
    print("[OK] test_code_modify_intent")
    test_not_code_modify_ops()
    print("[OK] test_not_code_modify_ops")
    test_moa_registry_open_to_all()
    print("[OK] test_moa_registry_open_to_all")
    test_allow_moa_registry_in_readonly()
    print("[OK] test_allow_moa_registry_in_readonly")
    print("[PASS] code_modify_permission")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
