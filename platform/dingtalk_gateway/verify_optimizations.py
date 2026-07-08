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


def test_env_check_blocked() -> None:
    from env_check_guard import (
        env_check_denial_message,
        guard_env_check_agent_reply,
        looks_like_env_check_request,
        looks_like_doctor_output,
    )

    for text in ("环境检查", "检查环境", "检查环境配置", "doctor", "运行环境检查"):
        assert looks_like_env_check_request(text), text
        assert not try_route(text).handled, f"不应走快捷路由: {text!r}"
    assert not looks_like_env_check_request("哪些cookie需要更新")
    assert not looks_like_env_check_request("帮我检查环境配置问题")
    assert looks_like_doctor_output("❌ 环境检查未通过。【凭证有效性】")
    assert guard_env_check_agent_reply("❌ 环境检查未通过", prompt="环境检查") == env_check_denial_message()


def test_env_check_not_fast_route() -> None:
    from route_patterns import is_likely_fast_route, normalize_fuzzy_fast_command

    for text in ("环境检查", "检查环境", "检查环境配置", "doctor"):
        assert not try_route(text).handled, f"不应走快捷路由: {text!r}"
        assert normalize_fuzzy_fast_command(text) is None, text
        assert not is_likely_fast_route(text), text
    assert not try_route("帮我检查环境配置问题").handled


def test_moa_check_fuzzy() -> None:
    for text in ("MOA检查", "检查MOA", "检查MOA环境", "MOA探活", "moa check"):
        result = try_route(text)
        assert result.handled, f"应路由: {text!r}"
    assert not try_route("不要看到MOA就进行检查").handled
    assert not try_route("帮我 MOA 探活").handled
    assert not try_route("提问 MOA 检查").handled
    for text in (
        "这是根据家族 id 获取所有家族成员 id 的 MOA，帮我入库",
        "帮我把MOA入库",
        "这是发送小时榜全服通知的MOA，帮我入库",
    ):
        assert not try_route(text).handled, f"入库任务不应走 MOA检查: {text!r}"
        from route_patterns import normalize_fuzzy_fast_command, is_likely_fast_route

        assert normalize_fuzzy_fast_command(text) is None, text
        assert not is_likely_fast_route(text), text


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
    from progress_message import build_heartbeat_message

    msg = build_heartbeat_message(session)
    assert "仍在执行中" in msg
    assert "Agent 执行中" not in msg
    assert "预计还需" not in msg


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

    assert suggest_command_hint("帮我 MOA 探活") is None
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
    from route_patterns import (
        is_likely_fast_route,
        normalize_fuzzy_fast_command,
        normalize_report_prompt,
    )

    assert normalize_report_prompt("帮我生成2.5.4版本测试报告") == "2.5.4版本生成测试报告"
    assert is_likely_fast_route("帮我生成2.5.4版本测试报告")
    assert normalize_fuzzy_fast_command("帮我 MOA 探活") is None
    assert not is_likely_fast_route("不要看到MOA就进行检查")
    assert normalize_fuzzy_fast_command("平台说明书在哪") == "工具平台"


def test_code_modify_guard() -> None:
    from code_modify_guard import guard_readonly_agent_reply

    raw = "已修改 dingtalk_gateway/server.py 的逻辑"
    out = guard_readonly_agent_reply(raw, allow_code_modify=False)
    assert "只读模式" in out


def test_gift_default_route() -> None:
    from gift_defaults import is_backpack_gift_request, should_use_gift_http

    assert should_use_gift_http("用户 8250 给 100465989 送礼物 2005004730")
    assert not should_use_gift_http("背包送礼 8250 给 100465989")
    assert is_backpack_gift_request("MOA背包下发 Ocean Gem")


def test_adb_execution_guard() -> None:
    from adb_execution_guard import looks_like_adb_execution_request

    assert looks_like_adb_execution_request("python3 adb/adb_execute.py macro 切换我的底栏")
    assert looks_like_adb_execution_request("真机打开礼物面板送礼")
    assert looks_like_adb_execution_request("flow run 进房送礼")
    assert not looks_like_adb_execution_request("Stage 用户 8250 私聊给 100465989 送礼物 2005056028")
    assert not looks_like_adb_execution_request("tunnel 查 100465989 gift/send")
    assert not looks_like_adb_execution_request("查询用户 100465989 详情")


def test_gateway_status_notify() -> None:
    import os
    from unittest.mock import patch

    from gateway_status_notify import (
        notify_gateway_started,
        notify_gateway_stopping,
        resolve_notify_conversation_id,
        touch_notify_group,
    )

    class FakeIncoming:
        conversation_type = "2"
        conversation_id = "cidTestGroup=="
        conversation_title = "测试群"

    with tempfile.TemporaryDirectory() as tmp:
        notify_path = Path(tmp) / "notify_group.json"
        restart_path = Path(tmp) / "restart_context.json"
        with patch("gateway_status_notify.NOTIFY_DATA", notify_path):
            with patch("gateway_restart.RESTART_CONTEXT", restart_path):
                touch_notify_group(FakeIncoming())  # type: ignore[arg-type]
                assert resolve_notify_conversation_id() == "cidTestGroup=="

                sent: list[str] = []

                def fake_send(text: str, *, client=None) -> bool:  # noqa: ARG001
                    sent.append(text)
                    return True

                restart_path.write_text(
                    json.dumps(
                        {
                            "trigger": "code_update",
                            "operator": "陈墨",
                            "changedFiles": ["platform/dingtalk_gateway/server.py"],
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                with patch("gateway_status_notify.send_proactive_group_text", fake_send):
                    with patch("gateway_status_notify._executor_hostname", return_value="test-host"):
                        notify_gateway_started()
                        notify_gateway_stopping(reason="测试停止")
                        notify_gateway_stopping(reason="重复")
                assert len(sent) == 2
                assert "代码更新后重启" in sent[0]
                assert "陈墨" in sent[0]
                assert "server.py" in sent[0]
                assert "已关闭" in sent[1]
                assert "测试停止" in sent[1]
                assert not restart_path.is_file()

        old = os.environ.pop("DINGTALK_NOTIFY_CONVERSATION_ID", None)
        try:
            os.environ["DINGTALK_NOTIFY_CONVERSATION_ID"] = "cidFromEnv=="
            assert resolve_notify_conversation_id() == "cidFromEnv=="
        finally:
            os.environ.pop("DINGTALK_NOTIFY_CONVERSATION_ID", None)
            if old is not None:
                os.environ["DINGTALK_NOTIFY_CONVERSATION_ID"] = old


def test_duration_history() -> None:
    import tempfile
    from pathlib import Path

    from duration_history import DurationHistoryStore, classify_task_kind

    assert classify_task_kind("MOA检查") == "fast:moa_check"
    assert classify_task_kind("查询用户 100465989") == "agent:query"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "duration_history.json"
        store = DurationHistoryStore(path=path)
        store.record("agent:query", 80.0, status="ok")
        store.record("agent:query", 120.0, status="ok")
        store.record("agent:query", 999.0, status="error")
        assert store.estimate_seconds("agent:query") == 100.0
        reloaded = DurationHistoryStore(path=path)
        assert reloaded.estimate_seconds("agent:query") == 100.0


def test_gateway_code_restart() -> None:
    import json
    import time
    from unittest.mock import patch

    from gateway_restart import (
        list_gateway_files_changed_since,
        read_and_clear_restart_context,
        write_restart_context,
    )

    with tempfile.TemporaryDirectory() as tmp:
        gateway_dir = Path(tmp) / "platform" / "dingtalk_gateway"
        gateway_dir.mkdir(parents=True)
        sample = gateway_dir / "server.py"
        sample.write_text("# test\n", encoding="utf-8")
        now = time.time()
        with patch("gateway_restart.GATEWAY_DIR", gateway_dir):
            with patch("gateway_restart.REPO_ROOT", Path(tmp)):
                changed = list_gateway_files_changed_since(now - 5)
                assert any(p.endswith("server.py") for p in changed)
                assert not list_gateway_files_changed_since(now + 60)

        ctx_path = Path(tmp) / "restart_context.json"
        with patch("gateway_restart.RESTART_CONTEXT", ctx_path):
            write_restart_context(operator="测试", changed_files=["platform/dingtalk_gateway/server.py"])
            ctx = read_and_clear_restart_context()
            assert ctx is not None
            assert ctx.get("trigger") == "code_update"
            assert ctx.get("operator") == "测试"
            assert read_and_clear_restart_context() is None


def main() -> int:
    test_env_check_blocked()
    print("[OK] test_env_check_blocked")
    test_env_check_not_fast_route()
    print("[OK] test_env_check_not_fast_route")
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
    test_gift_default_route()
    print("[OK] test_gift_default_route")
    test_adb_execution_guard()
    print("[OK] test_adb_execution_guard")
    test_gateway_status_notify()
    print("[OK] test_gateway_status_notify")
    test_duration_history()
    print("[OK] test_duration_history")
    test_gateway_code_restart()
    print("[OK] test_gateway_code_restart")
    print("[PASS] gateway optimizations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
