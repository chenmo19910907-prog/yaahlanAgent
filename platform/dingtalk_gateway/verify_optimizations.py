#!/usr/bin/env python3
"""离线验证网关优化项：路由模糊匹配、日志脱敏、会话持久化。"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from command_router import try_route
from conversation_store import ConversationStore
from log_redact import redact_for_log


def test_env_check_fuzzy() -> None:
    for text in ("环境检查", "检查环境", "检查环境配置", "doctor"):
        result = try_route(text)
        assert result.handled, f"应路由: {text!r}"
    assert not try_route("帮我检查环境配置问题").handled


def test_moa_check_fuzzy() -> None:
    for text in ("MOA检查", "检查MOA", "检查MOA环境", "MOA探活", "moa check"):
        result = try_route(text)
        assert result.handled, f"应路由: {text!r}"


def test_help_fuzzy() -> None:
    for text in ("帮助", "使用帮助", "能力说明", "说明书", "新手引导"):
        result = try_route(text)
        assert result.handled, f"应路由: {text!r}"


def test_catalog_fuzzy() -> None:
    from route_patterns import CATALOG_OPEN_RE

    for text in ("工具平台", "工具平台清单", "平台说明书", "打开工具台"):
        assert CATALOG_OPEN_RE.match(text), f"应匹配: {text!r}"


def test_queue_and_progress() -> None:
    from progress_message import build_queue_message
    from task_session import TaskSession

    assert "预计等待" in build_queue_message(1)
    session = TaskSession()
    session.begin("x", budget_s=600)
    session.set_phase("agent")
    from progress_message import build_heartbeat_message

    msg = build_heartbeat_message(session)
    assert "Agent 执行中" in msg


def test_log_redact() -> None:
    raw = "cookie=abc123secret token=Bearer xyz789 " + ("x" * 200)
    out = redact_for_log(raw, max_len=80)
    assert "abc123" not in out
    assert "xyz789" not in out
    assert len(out) <= 80


def test_conversation_persistence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "conversations.json"
        store = ConversationStore(index_path=path)
        store.save("cid1", "查询用户 123", sender_staff_id="u1")
        store.save_full_reply("cid1", "用户详情…", sender_staff_id="u1")

        reloaded = ConversationStore(index_path=path)
        assert reloaded.get_last("cid1", sender_staff_id="u1") == "查询用户 123"
        assert reloaded.get_last_full_reply("cid1", sender_staff_id="u1") == "用户详情…"

        data = json.loads(path.read_text(encoding="utf-8"))
        assert "cid1:user:u1" in data


def test_command_hints() -> None:
    from command_hints import suggest_command_hint

    hint = suggest_command_hint("帮我 MOA 探活")
    assert hint is not None and "MOA检查" in hint
    assert suggest_command_hint("查询用户 100465989 详情") is None


def test_format_exception_friendly() -> None:
    from reply_formatter import format_exception

    msg = format_exception(RuntimeError("Agent 启动失败: internal error"))
    assert "重新执行" in msg
    assert "internal error" not in msg


def test_truncate_guide() -> None:
    from export_delivery import _truncate_inline

    long_text = "x" * 5000
    out = _truncate_inline(long_text)
    assert "查看全部数据" in out
    assert "导出到钉钉文档" in out


def test_report_nl_route() -> None:
    from route_patterns import normalize_report_prompt, is_likely_fast_route

    assert normalize_report_prompt("帮我生成2.5.4版本测试报告") == "2.5.4版本生成测试报告"
    assert is_likely_fast_route("帮我生成2.5.4版本测试报告")


def test_code_modify_guard() -> None:
    from code_modify_guard import guard_readonly_agent_reply

    raw = "已修改 dingtalk_gateway/server.py 的逻辑"
    out = guard_readonly_agent_reply(raw, allow_code_modify=False)
    assert "只读模式" in out


def main() -> int:
    test_env_check_fuzzy()
    print("[OK] test_env_check_fuzzy")
    test_moa_check_fuzzy()
    print("[OK] test_moa_check_fuzzy")
    test_help_fuzzy()
    print("[OK] test_help_fuzzy")
    test_catalog_fuzzy()
    print("[OK] test_catalog_fuzzy")
    test_queue_and_progress()
    print("[OK] test_queue_and_progress")
    test_log_redact()
    print("[OK] test_log_redact")
    test_conversation_persistence()
    print("[OK] test_conversation_persistence")
    test_command_hints()
    print("[OK] test_command_hints")
    test_format_exception_friendly()
    print("[OK] test_format_exception_friendly")
    test_truncate_guide()
    print("[OK] test_truncate_guide")
    test_report_nl_route()
    print("[OK] test_report_nl_route")
    test_code_modify_guard()
    print("[OK] test_code_modify_guard")
    print("[PASS] gateway optimizations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
