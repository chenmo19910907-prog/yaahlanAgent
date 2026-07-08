#!/usr/bin/env python3
"""Agent 流式 Markdown 渲染单测（无需钉钉 / Cursor）。"""

from __future__ import annotations

from agent_stream_card import AgentStreamCard
from agent_stream_renderer import AgentStreamRenderer, assistant_text_chunk


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
    assert "msgContent" in _CARD_ORDER
    assert _CARD_ORDER.index("staticMsgContent") < _CARD_ORDER.index("msgContent")


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

    long_prompt = build_streaming_card_header("文字", prompt="A" * 200)
    assert long_prompt.count("A") <= 121
    assert "…" in long_prompt


def test_progress_not_double_header() -> None:
    import time

    from agent_stream_card import AgentStreamCard

    card = AgentStreamCard.__new__(AgentStreamCard)
    card._header = "已收到（文字），执行中… 可发「中断操作」打断。"
    card._persistent_header = "**提问** 用两句话介绍 platform 目录"
    card._card_title = "提问：用两句话介绍 platform 目录"
    card._agent_body = ""
    card._batch_progress_line = ""
    card._started_at = time.monotonic()
    card._status_line = card._format_progress_markdown()
    assert "已收到" not in card._status_line
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

    card.begin_running("已收到（文字），执行中…")
    assert card._md_card.update.call_count == 1
    assert card._md_card.reply.call_count == 0


def test_persistent_header_survives_finish() -> None:
    from agent_stream_card import AgentStreamCard

    card = AgentStreamCard.__new__(AgentStreamCard)
    card._header = "已收到（文字），执行中… 可发「中断操作」打断。"
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


def test_finish_status_keeps_agent_body() -> None:
    """完成时保留历史 Agent 文本，终态提示作为末行状态。"""
    import threading
    from unittest.mock import MagicMock

    from agent_stream_card import AgentStreamCard

    card = AgentStreamCard.__new__(AgentStreamCard)
    card._mode = "markdown"
    card._started = True
    card._header = "已收到（文字），执行中…"
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
    assert "已完成对 13311111111 的登录状态查询。" in flushed
    assert "执行完成" in flushed
    assert "已收到" not in flushed  # 瞬态 header 已清
    assert flushed.index("已完成对") < flushed.index("执行完成")


def test_three_channels_coexist() -> None:
    """Agent 文本 / 已用时 / 批量进度三通道同时展示。"""
    from agent_stream_card import AgentStreamCard

    card = AgentStreamCard.__new__(AgentStreamCard)
    card._header = "已收到（文字），执行中…"
    card._card_title = "提问：批量发钻"
    card._agent_body = "正在再次执行批量发钻。"
    card._status_line = "执行中，已用时 15秒…"
    card._batch_progress_line = "批量操作进度：已完成 2/5 项（发钻石）"
    composed = card._compose_body()
    assert "提问：" not in composed
    assert "正在再次执行批量发钻。" in composed
    assert "执行中，已用时 15秒" in composed
    assert "批量操作进度：已完成 2/5 项" in composed
    # 三通道顺序：Agent 文本 → 已用时 → 批量进度
    assert composed.index("正在再次执行") < composed.index("执行中，已用时")
    assert composed.index("执行中，已用时") < composed.index("批量操作进度")


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


def main() -> int:
    test_thinking_and_answer()
    test_tool_lines()
    test_markdown_for_card_compact()
    test_update_answer_snapshot_vs_delta()
    test_empty_defaults()
    test_assistant_chunk()
    test_card_order_excludes_slider()
    test_streaming_enabled_default()
    test_streaming_card_header()
    test_progress_not_double_header()
    test_reuse_preassigned_card_without_second_start()
    test_persistent_header_survives_finish()
    test_finish_status_keeps_agent_body()
    test_three_channels_coexist()
    test_ensure_stream_state_on_legacy_instance()
    test_streaming_card_title()
    test_preserve_markdown_reply()
    print("[PASS] agent_stream_renderer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
