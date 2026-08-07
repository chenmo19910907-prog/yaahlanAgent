#!/usr/bin/env python3
"""Agent 流式 Markdown 渲染单测（无需钉钉 / Cursor）。"""

from __future__ import annotations

from agent_stream_card import AgentStreamCard
from agent_stream_renderer import (
    AgentStreamRenderer,
    append_process_summary,
    assistant_text_chunk,
)


def test_thinking_and_answer() -> None:
    r = AgentStreamRenderer()
    assert r.apply({"type": "thinking-delta", "text": "先查 registry"})
    assert r.apply({"type": "text-delta", "text": "已完成。"})
    md = r.markdown()
    assert "思考中" in md
    assert "已完成。" in md


def test_tool_lines() -> None:
    r = AgentStreamRenderer()
    r.apply({"type": "tool-call-started", "toolCall": {"name": "Shell"}})
    r.apply({"type": "tool-call-completed", "toolCall": {"name": "Shell"}})
    md = r.markdown()
    assert "🔧 Shell" in md
    assert "✅ Shell" in md


def test_empty_defaults() -> None:
    assert AgentStreamRenderer().markdown() == "⏳ Agent 启动中…"


def test_assistant_chunk() -> None:
    class Block:
        def __init__(self, text: str) -> None:
            self.text = text

    class Content:
        content = (Block("你"), Block("好"))

    class Msg:
        type = "assistant"
        message = Content()

    assert assistant_text_chunk(Msg()) == "你好"


def test_card_order_excludes_slider() -> None:
    from agent_stream_card import _CARD_ORDER

    assert "msgSlider" not in _CARD_ORDER
    assert "msgButtons" not in _CARD_ORDER
    assert "msgContent" in _CARD_ORDER
    assert _CARD_ORDER.index("staticMsgContent") < _CARD_ORDER.index("msgContent")


def test_ai_card_mode_downgrades_without_feedback_flag() -> None:
    import os
    from unittest.mock import patch

    from agent_stream_card import _card_mode

    prev_card = os.environ.get("DINGTALK_AGENT_STREAMING_CARD")
    prev_feedback = os.environ.get("DINGTALK_AGENT_STREAMING_CARD_FEEDBACK")
    try:
        with patch("env_loader.load_env_local"):
            os.environ["DINGTALK_AGENT_STREAMING_CARD"] = "ai"
            os.environ.pop("DINGTALK_AGENT_STREAMING_CARD_FEEDBACK", None)
            assert _card_mode() == "markdown"
            os.environ["DINGTALK_AGENT_STREAMING_CARD_FEEDBACK"] = "1"
            assert _card_mode() == "ai"
    finally:
        if prev_card is None:
            os.environ.pop("DINGTALK_AGENT_STREAMING_CARD", None)
        else:
            os.environ["DINGTALK_AGENT_STREAMING_CARD"] = prev_card
        if prev_feedback is None:
            os.environ.pop("DINGTALK_AGENT_STREAMING_CARD_FEEDBACK", None)
        else:
            os.environ["DINGTALK_AGENT_STREAMING_CARD_FEEDBACK"] = prev_feedback


def test_streaming_enabled_default() -> None:
    from agent_stream_card import is_agent_streaming_enabled

    assert is_agent_streaming_enabled() is True


def test_streaming_card_header() -> None:
    from progress_message import build_streaming_ack, build_streaming_card_header

    header = build_streaming_card_header("文字")
    assert "已收到（文字）" in header
    assert "中断操作" in header

    with_prompt = build_streaming_card_header("文字", prompt="用两句话介绍 platform 目录")
    assert "**提问**" in with_prompt
    assert "用两句话介绍 platform 目录" in with_prompt
    assert with_prompt.count("已收到（文字）") == 1
    assert "预计约" in with_prompt or "预计约3分钟以上" in with_prompt

    ack = build_streaming_ack("文字", prompt="用两句话介绍 platform 目录")
    assert "预计约" in ack or "预计约3分钟以上" in ack
    assert "已收到（文字）" in ack
    assert "，可发「中断操作」" in ack
    assert "，执行中" not in ack

    long_prompt = build_streaming_card_header("文字", prompt="A" * 200)
    assert long_prompt.count("A") <= 121
    assert "…" in long_prompt


def test_streaming_progress_status_line() -> None:
    from progress_message import build_streaming_progress_status_line

    line = build_streaming_progress_status_line(21.0, estimate_s=180.0)
    assert line == "执行中，已用时 21秒…"
    assert "预计还需" not in line
    assert "中断操作" not in line

    no_eta = build_streaming_progress_status_line(10.0)
    assert no_eta == "执行中，已用时 10秒…"
    assert "预计还需" not in no_eta
    assert "中断操作" not in no_eta


def test_progress_not_double_header() -> None:
    import time

    from agent_stream_card import AgentStreamCard

    card = AgentStreamCard.__new__(AgentStreamCard)
    card._header = "已收到（文字），可发「中断操作」打断。"
    card._persistent_header = "**提问** 用两句话介绍 platform 目录"
    card._card_title = "提问：用两句话介绍 platform 目录"
    card._agent_body = ""
    card._batch_progress_line = ""
    card._estimate_seconds = 180.0
    card._started_at = time.monotonic()
    card._status_line = card._format_progress_markdown()
    assert "已收到" not in card._status_line
    assert "执行中，已用时" in card._status_line
    assert "预计还需" not in card._status_line
    assert "中断操作" not in card._status_line
    composed = card._compose_body()
    assert composed.count("已收到（文字）") == 1
    assert "**提问**" not in composed


def test_preserve_markdown_reply() -> None:
    from reply_formatter import format_group_reply

    raw = (
        "| 模块 | 说明 |\n| --- | --- |\n| platform | 能力汇总 |\n\n"
        "```bash\nls platform\n```"
    )
    plain = format_group_reply(raw, prompt="介绍 platform")
    md = format_group_reply(raw, prompt="介绍 platform", preserve_markdown=True)
    assert "| platform |" in md
    assert "```bash" in md
    assert "ls platform" in plain
    assert "| platform |" not in plain


def test_begin_running_clears_queue_body() -> None:
    """排队态转入执行态时清除 _agent_body 中的排队文案。"""
    import time

    from agent_stream_card import AgentStreamCard

    card = AgentStreamCard.__new__(AgentStreamCard)
    card._mode = "markdown"
    card._started = True
    card._header = ""
    card._persistent_header = "> **提问**\n> 测试"
    card._card_title = "提问：测试"
    card._min_interval_s = 0.0
    card._last_push_at = 0.0
    card._lock = __import__("threading").Lock()
    card._pending = None
    card._timer = None
    card._push_count = 0
    card._progress_timer = None
    card._agent_body = "排队中（前面约 2 个，预计等待约 6分钟）<br>可发「中断操作」打断。"
    card._status_line = ""
    card._batch_progress_line = ""
    card._estimate_seconds = 180.0
    card._started_at = time.monotonic()
    card._last_content_at = card._started_at
    card._last_flushed_body = card._agent_body
    card._card_instance_id = "id"
    card._md_card = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    card._ai_card = None

    card.begin_running("已收到（文字），可发「中断操作」打断。")
    composed = card._compose_body()
    assert "排队中" not in composed
    assert "已收到（文字）" in composed
    assert "执行中，已用时" in composed


def test_reuse_preassigned_card_without_second_start() -> None:
    """预分配卡片已 start 后，begin_running 只 update 不 reply。"""
    from agent_stream_card import AgentStreamCard

    card = AgentStreamCard.__new__(AgentStreamCard)
    card._mode = "markdown"
    card._started = True
    card._header = ""
    card._persistent_header = "> **提问**\n> 测试"
    card._card_title = "提问：测试"
    card._min_interval_s = 0.0
    card._last_push_at = 0.0
    card._lock = __import__("threading").Lock()
    card._pending = None
    card._timer = None
    card._push_count = 0
    card._progress_timer = None
    card._agent_body = ""
    card._status_line = ""
    card._batch_progress_line = ""
    card._started_at = 0.0
    card._last_content_at = 0.0
    card._card_instance_id = "id"
    card._md_card = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    card._ai_card = None

    card.begin_running("已收到（文字）")
    assert card._md_card.update.call_count == 1
    assert card._md_card.reply.call_count == 0


def test_persistent_header_survives_finish() -> None:
    from agent_stream_card import AgentStreamCard

    card = AgentStreamCard.__new__(AgentStreamCard)
    card._header = "已收到（文字），可发「中断操作」打断。"
    card._persistent_header = "**提问** 用两句话介绍 platform 目录"
    card._card_title = "提问：用两句话介绍 platform 目录"
    card._agent_body = "⏳ 执行中，已用时 10秒…"
    card._status_line = ""
    card._batch_progress_line = ""

    running = card._compose_body()
    assert "已收到" in running
    assert "**提问**" not in running

    card._header = ""
    card._agent_body = "platform 目录是能力汇总层。\n\n⏱ 本次耗时 39秒"
    final = card._compose_body()
    assert "已收到" not in final
    assert "本次耗时" in final
    assert card._card_title == "提问：用两句话介绍 platform 目录"


def test_finish_status_clears_agent_body() -> None:
    """完成时清空 Agent 流式正文，Markdown 卡片正文仅保留完成提示。"""
    import threading
    from unittest.mock import MagicMock

    from agent_stream_card import AgentStreamCard

    card = AgentStreamCard.__new__(AgentStreamCard)
    card._mode = "markdown"
    card._started = True
    card._header = "已收到（文字）"
    card._persistent_header = ""
    card._card_title = "提问：查询登录状态"
    card._min_interval_s = 0.0
    card._last_push_at = 0.0
    card._lock = threading.Lock()
    card._pending = "x"
    card._timer = None
    card._push_count = 0
    card._progress_timer = None
    card._agent_body = "已完成对 13311111111 的登录状态查询。"
    card._status_line = "执行中，已用时 19秒…"
    card._batch_progress_line = ""
    card._started_at = 0.0
    card._last_content_at = 0.0
    card._last_flushed_body = ""
    card._card_instance_id = "id"
    card._md_card = MagicMock()
    card._ai_card = None

    card.finish_status("✅ 执行完成，结果见下方消息 ↓")

    flushed = card._md_card.update.call_args[0][0]
    assert "已完成对 13311111111 的登录状态查询。" not in flushed
    assert flushed.strip() == "✅ 执行完成，结果见下方消息 ↓"
    assert "已收到" not in flushed  # 瞬态 header 已清


def test_finish_status_ai_clears_truncated_body_and_sets_title() -> None:
    """AI 卡片完成态：提问写入 static 区，流式区仅保留完成提示。"""
    import threading
    from unittest.mock import MagicMock

    from agent_stream_card import AgentStreamCard

    card = AgentStreamCard.__new__(AgentStreamCard)
    card._mode = "ai"
    card._started = True
    card._header = ""
    card._persistent_header = "**提问** 试一下效果"
    card._card_title = "提问：试一下效果"
    card._min_interval_s = 0.0
    card._last_push_at = 0.0
    card._lock = threading.Lock()
    card._pending = "x"
    card._timer = None
    card._push_count = 0
    card._progress_timer = None
    card._agent_body = "…模式（当前） |<br>| — | — | — |"
    card._status_line = "执行中，已用时 30秒…"
    card._batch_progress_line = ""
    card._started_at = 0.0
    card._last_content_at = 0.0
    card._last_flushed_body = ""
    card._card_instance_id = "id"
    card._md_card = None
    card._ai_card = MagicMock()
    card._ai_card.card_instance_id = "id"

    card.finish_status("✅ 执行完成，结果见下方消息 ↓")

    card._ai_card.set_title_and_logo.assert_called_with("提问：试一下效果", "")
    assert card._ai_card.static_markdown == ""
    assert card._ai_card.markdown == "✅ 执行完成，结果见下方消息 ↓"
    assert "…模式（当前）" not in (card._ai_card.markdown or "")
    card._ai_card.ai_finish.assert_called_once()
    card._ai_card.ai_streaming.assert_not_called()


def test_compose_ai_static_only_extra() -> None:
    from agent_stream_card import AgentStreamCard

    card = AgentStreamCard.__new__(AgentStreamCard)
    card._card_title = "提问：hello"
    card._persistent_header = "**提问** hello"
    assert card._compose_ai_static() == ""
    assert card._compose_ai_static(extra="✅ done") == "✅ done"


def test_three_channels_coexist() -> None:
    """Agent 文本 / 已用时 / 批量进度三通道同时展示。"""
    from agent_stream_card import AgentStreamCard

    card = AgentStreamCard.__new__(AgentStreamCard)
    card._header = "已收到（文字）"
    card._card_title = "提问：批量发钻"
    card._agent_body = "正在再次执行批量发钻。"
    card._status_line = "执行中，已用时 15秒…"
    card._batch_progress_line = "批量操作进度：已完成 2/5 项（发钻石）"
    composed = card._compose_body()
    assert "提问：" not in composed
    assert "正在再次执行批量发钻。" in composed
    assert "执行中，已用时 15秒…" in composed
    assert "批量操作进度：已完成 2/5 项" in composed
    # 三通道顺序：Agent 文本 → 批量进度 → 已用时
    assert composed.index("正在再次执行") < composed.index("批量操作进度")
    assert composed.index("批量操作进度") < composed.index("执行中，已用时")


def test_streaming_card_title() -> None:
    from progress_message import build_streaming_card_title

    assert build_streaming_card_title("123") == "提问：123"
    assert build_streaming_card_title("") == ""


def test_markdown_for_card_compact() -> None:
    r = AgentStreamRenderer()
    r.append_tool_step("Shell")
    compact = r.markdown_for_card()
    assert "Shell" in compact
    assert "🔧" not in compact
    assert "\n\n" not in compact

    r2 = AgentStreamRenderer()
    r2.apply({"type": "thinking-delta", "text": "很长的思考" * 50})
    assert r2.markdown_for_card() == "思考中…"


def test_markdown_for_web_detailed_thinking() -> None:
    r = AgentStreamRenderer()
    r.apply({"type": "thinking-delta", "text": "先查 Admin\n再核对 Tunnel 抓包"})
    r.apply({"type": "tool-call-started", "toolCall": {"name": "Shell"}})
    md = r.markdown_for_web()
    assert "思考中" in md
    assert "先查 Admin" in md
    assert "Tunnel 抓包" in md
    assert "先查 Admin\n再核对 Tunnel 抓包" in md
    assert "### 执行工作" in md
    assert "Shell" in md
    assert md != "思考中…"


def test_markdown_for_web_multiline_thinking() -> None:
    r = AgentStreamRenderer()
    r.apply(
        {
            "type": "thinking-delta",
            "text": "先查本地 registry 和 mappings\n无登记则继续查服务端",
        }
    )
    md = r.markdown_for_web()
    assert "先查本地 registry 和 mappings" in md
    assert "无登记则继续查服务端" in md
    assert "先查本地 registry 和 mappings\n无登记则继续查服务端" in md


def test_markdown_for_web_early_answer_as_thinking() -> None:
    """工具调用前 assistant 流式正文应归入思考区（SDK 常无 thinkingMessage）。"""
    r = AgentStreamRenderer()
    r.update_answer("正在了解 Web Agent 的思考操作流程")
    md = r.markdown_for_web()
    payload = r.web_process_payload()
    assert "### 思考中" in md
    assert "正在了解 Web Agent" in md
    assert payload["thinking"] == "正在了解 Web Agent 的思考操作流程"
    r.append_tool_step("Grep")
    payload2 = r.web_process_payload()
    assert payload2["thinking"] == "正在了解 Web Agent 的思考操作流程"
    md2 = r.markdown_for_web()
    assert "### 思考中" in md2
    assert "### 执行工作" in md2
    assert "Grep" in md2


def test_sanitize_web_thinking_strips_prompt_echo() -> None:
    from agent_stream_renderer import sanitize_web_thinking

    raw = "正在回顾 Web Agent 相关上下文与近期改动，以便继续深入思考。\n用户"
    assert sanitize_web_thinking(raw) == (
        "正在回顾 Web Agent 相关上下文与近期改动，以便继续深入思考。"
    )
    assert sanitize_web_thinking("用户消息（延续当前 Web Agent 对话）：") == ""


def test_update_thinking_snapshot_vs_delta() -> None:
    r = AgentStreamRenderer()
    assert r.update_thinking("先查本地")
    assert r.update_thinking("先查本地 registry")
    assert r._thinking == "先查本地 registry"

    r2 = AgentStreamRenderer()
    r2.update_thinking("第一段")
    r2.update_thinking("第二段")
    assert r2._thinking == "第一段第二段"


def test_markdown_for_web_long_thinking_tail() -> None:
    r = AgentStreamRenderer()
    from agent_stream_renderer import WEB_THINKING_MAX_CHARS

    r.apply({"type": "thinking-delta", "text": "x" * (WEB_THINKING_MAX_CHARS + 200)})
    md = r.markdown_for_web()
    assert md.startswith("### 思考中")
    assert len(md) < WEB_THINKING_MAX_CHARS + 200
    assert md.count("x") >= WEB_THINKING_MAX_CHARS - 20


def test_update_answer_snapshot_vs_delta() -> None:
    # 全量快照增长：替换而非重复
    r = AgentStreamRenderer()
    assert r.update_answer("正在检查")
    assert r.update_answer("正在检查上次批量查询")
    assert r._answer == "正在检查上次批量查询"

    # 不重叠的新片段：追加
    r2 = AgentStreamRenderer()
    r2.update_answer("第一段。")
    r2.update_answer("第二段。")
    assert r2._answer == "第一段。第二段。"

    # 旧快照更短（乱序到达）：忽略
    r3 = AgentStreamRenderer()
    r3.update_answer("完整的一句话")
    assert not r3.update_answer("完整")
    assert r3._answer == "完整的一句话"


def test_ensure_stream_state_on_legacy_instance() -> None:
    """旧实例缺字段时不抛 AttributeError。"""
    from agent_stream_card import AgentStreamCard

    card = AgentStreamCard.__new__(AgentStreamCard)
    card._started = True
    card._header = "已收到"
    card._started_at = 0.0
    card._lock = __import__("threading").Lock()
    card._pending = None
    card._timer = None
    card._min_interval_s = 0.0
    card._last_push_at = 0.0
    card._push_count = 0
    card._mode = "markdown"
    card._card_title = ""
    card._card_instance_id = "id"
    card._md_card = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    card._ai_card = None
    card._progress_timer = None
    card._ensure_stream_state()
    card._render()
    assert hasattr(card, "_last_flushed_body")


def test_process_summary_for_final() -> None:
    r = AgentStreamRenderer()
    r.apply({"type": "thinking-delta", "text": "先查 Admin 再核对 Tunnel"})
    r.apply({"type": "tool-call-started", "toolCall": {"name": "Shell"}})
    r.apply({"type": "tool-call-completed", "toolCall": {"name": "Shell"}})
    summary = r.process_summary_markdown()
    assert "### 思考过程" in summary
    assert "Admin" in summary
    assert "### 执行工作" in summary
    assert "Shell" in summary
    merged = append_process_summary("结论正文", summary)
    assert merged.startswith("结论正文")
    assert "---" in merged
    assert "### 思考过程" in merged


def test_sanitize_web_thinking_strips_prompt_echo() -> None:
    from agent_stream_renderer import sanitize_web_thinking

    raw = "正在排查问题\n用户\n用户消息（延续当前 Web Agent 对话）：\n继续分析"
    cleaned = sanitize_web_thinking(raw)
    assert "正在排查问题" in cleaned
    assert "继续分析" in cleaned
    assert "用户消息" not in cleaned
    assert cleaned.strip() != "用户"


def test_web_process_payload_phase_before_thinking() -> None:
    r = AgentStreamRenderer()
    r.set_status_hint("Agent 已启动…")
    assert r.markdown_for_web() == ""
    payload = r.web_process_payload()
    assert payload.get("phase") == "Agent 已启动…"
    assert payload.get("thinking") == ""
    r.apply({"type": "thinking-delta", "text": "先查 Admin"})
    payload2 = r.web_process_payload()
    assert "phase" not in payload2
    assert "先查 Admin" in payload2["thinking"]


def main() -> int:
    test_thinking_and_answer()
    test_tool_lines()
    test_process_summary_for_final()
    test_markdown_for_card_compact()
    test_markdown_for_web_detailed_thinking()
    test_markdown_for_web_multiline_thinking()
    test_markdown_for_web_early_answer_as_thinking()
    test_sanitize_web_thinking_strips_prompt_echo()
    test_update_thinking_snapshot_vs_delta()
    test_markdown_for_web_long_thinking_tail()
    test_web_process_payload_phase_before_thinking()
    test_update_answer_snapshot_vs_delta()
    test_empty_defaults()
    test_assistant_chunk()
    test_card_order_excludes_slider()
    test_ai_card_mode_downgrades_without_feedback_flag()
    test_streaming_enabled_default()
    test_streaming_card_header()
    test_streaming_progress_status_line()
    test_progress_not_double_header()
    test_begin_running_clears_queue_body()
    test_reuse_preassigned_card_without_second_start()
    test_persistent_header_survives_finish()
    test_finish_status_clears_agent_body()
    test_finish_status_ai_clears_truncated_body_and_sets_title()
    test_compose_ai_static_only_extra()
    test_three_channels_coexist()
    test_ensure_stream_state_on_legacy_instance()
    test_streaming_card_title()
    test_preserve_markdown_reply()
    print("[PASS] agent_stream_renderer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
