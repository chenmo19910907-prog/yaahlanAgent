#!/usr/bin/env python3
"""验证服务端 Agent 问答概述落盘与最终回复拼接。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from service_agent_run_log import (  # noqa: E402
    append_service_agent_exchange,
    append_service_agent_summary_to_reply,
    build_service_agent_summary,
    clear_service_agent_run_log,
    dedupe_service_agent_summary_sections,
    normalize_qa_summary_format,
)
from web_prompt import finalize_web_reply_text  # noqa: E402


def main() -> int:
    user_key = "web:verify_service_agent_summary"
    with tempfile.TemporaryDirectory() as tmp:
        log_dir = Path(tmp) / "service_agent_run_log"
        import service_agent_run_log as mod  # noqa: WPS433

        mod.LOG_DIR = log_dir

        clear_service_agent_run_log(user_key)
        append_service_agent_exchange(
            user_key,
            question="VIP 获取时间字段是哪个？能否通过 MOA 修改？",
            answer=(
                "字段为 getVipInfo.startLevelTime，当前无公开 MOA 可写该时间。"
                "补充说明：该字段只读，来源于用户首次开通 VIP 的订单时间，"
                "不支持后台人工修改或批量导入。"
            ),
        )
        append_service_agent_exchange(
            user_key,
            question="provideDiamond 的 ServiceUrl 是什么？",
            answer=(
                "## 结论\n\n"
                "ServiceUrl 为 `/service/provide-diamond`。\n\n"
                "## 说明\n\n"
                "该接口用于发放钻石，需携带用户 token 与 roomId。"
            ),
        )

        summary = build_service_agent_summary(user_key)
        assert "服务端 Agent 问答概述" in summary
        assert "**1. 问**：VIP 获取时间字段是哪个？能否通过 MOA 修改？" in summary
        assert "**答**：字段为 getVipInfo.startLevelTime" in summary
        assert "批量导入" in summary
        assert "**2. 问**：provideDiamond 的 ServiceUrl 是什么？" in summary
        assert "**答**：" in summary
        assert "provide-diamond" in summary

        concise_summary = build_service_agent_summary(user_key, reply_mode="concise")
        assert "服务端 Agent 问答概述" in concise_summary
        assert "批量导入" not in concise_summary
        assert len(concise_summary) < len(summary)

        detailed_summary = build_service_agent_summary(user_key, reply_mode="detailed")
        assert "服务端 Agent 问答概述" in detailed_summary
        assert "provide-diamond" in detailed_summary
        assert "roomId" in detailed_summary
        assert "roomId" not in concise_summary

        final = finalize_web_reply_text(
            "结论：暂无法调整 VIP 获取时间。",
            12.5,
            task_kind="generic",
            reply_mode="standard",
            user_key=user_key,
        )
        assert "结论：暂无法调整 VIP 获取时间。" in final
        assert "服务端 Agent 问答概述" in final
        assert "本次耗时" in final

        concise = finalize_web_reply_text(
            "结论：无符合条件账号。",
            8.0,
            reply_mode="concise",
            user_key=user_key,
        )
        assert "服务端 Agent 问答概述" in concise
        assert "本次耗时" not in concise

        empty = finalize_web_reply_text("仅 MOA 查询。", 3.0, user_key="web:empty")
        assert "问答概述" not in empty

        agent_written = (
            "## 发红包实现\n\n两段式架构。\n\n"
            "---\n\n"
            "## 服务端 Agent 问答概述\n\n"
            "1. 问：发红包实现？ 答：Room 校验 + Base 落库。"
        )
        deduped = dedupe_service_agent_summary_sections(
            f"{agent_written}\n\n---\n\n{summary}"
        )
        assert deduped.count("问答概述") == 1
        assert "**1. 问**：发红包实现？" in deduped
        assert "**答**：Room 校验 + Base 落库。" in deduped
        assert append_service_agent_summary_to_reply(agent_written, user_key) == dedupe_service_agent_summary_sections(
            agent_written
        )

        normalized = normalize_qa_summary_format(
            "## 本地 Agent 问答概述\n\n"
            "**1. 问**：3+3等于多少？\n"
            "**答**：3+3=6。"
        )
        assert "**1. 问**：3+3等于多少？" in normalized
        assert "**答**：3+3=6。" in normalized

    print("verify_service_agent_summary: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
