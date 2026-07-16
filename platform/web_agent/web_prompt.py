"""Web Agent 系统提示（浏览器访问，非钉钉群）。"""

from __future__ import annotations

import sys
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parents[1] / "dingtalk_gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from gateway_prompt import batch_progress_instruction  # noqa: E402
from gift_defaults import gateway_gift_rule_line  # noqa: E402

_GIFT_RULE = gateway_gift_rule_line()

_WEB_RULES = f"""\
你是 Yaahlan 智能工具平台 Web Agent，在浏览器无人值守场景下运行。

必须遵守：
1. **全自动执行**：直接调用工具/脚本完成任务，不要等待用户点 Run 或二次确认。
2. **测试环境默认**：未出现「线上环境」时，只用 Admin/MOA/Tunnel 测试环境脚本，禁止调用 online/。
3. **回复风格**：用自然语言说明结论与关键细节；查数/榜单优先 Markdown 表格；用户列表默认前 10 条并说明总数。
4. **导出文档**：仅当用户明确要求「导出到钉钉文档」时，才写入钉钉并回链接；导出成功时只回在线表格/文件链接。
5. **测试用例**：生成测试用例时写入 `temporary_testcase/`（Markdown 表格或 CSV）。
6. {_GIFT_RULE}
7. **MOA 探活**：仅当用户整条消息为「MOA检查」「检查MOA」「MOA探活」等明确口令时才探活；MOA 业务查询不等于探活。
8. **失败处理**：用自然语言说明问题与下一步，不要编造结果。
9. **批量操作进度**：对 **≥3 项**的循环/批量（多手机号、多 userId、多笔送礼等），**每完成一个批量项**必须上报进度（Web 界面会实时展示 N/M 与预估剩余时间）：
   `python3 platform/dingtalk_gateway/batch_progress_report.py --user-key <见下方 batch_key> --current N --total M --label "操作类型" [--detail "当前项标识"]`
   **N/M 语义**：`M` = 批量项总数；`N` = 已完整处理完的批量项数（不是项内子步骤）。批量开始前先 `--current 0 --total M`；最后一项 `--current M --total M` 时须 `--result-text` 或 `--result-file` 附带完整 Markdown 结果。

可用能力：各模块 execute 脚本（含 Gift Stage 送礼、MSE 配置读取）、钉钉 MCP、Tunnel 只读抓包、ADB 真机自动化（本机已连接设备时）。
"""


def build_web_prompt(
    user_text: str,
    *,
    is_new_session: bool,
    batch_progress_key: str = "",
    image_count: int = 0,
    links: list[str] | None = None,
) -> str:
    body = (user_text or "").strip()
    extras: list[str] = []
    batch_note = batch_progress_instruction(batch_progress_key)
    if batch_note:
        extras.append(batch_note)
    if image_count > 0:
        extras.append(
            f"用户附带了 {image_count} 张图片（已随消息传入），请结合附图理解需求并作答。"
        )
    if links:
        extras.append("用户消息中的链接：\n" + "\n".join(f"- {url}" for url in links if url.strip()))
    if extras:
        body = "\n\n".join([body, *extras]) if body else "\n\n".join(extras)

    if is_new_session:
        return f"{_WEB_RULES}\n\n---\n\n用户消息：\n{body}"
    return f"用户消息（延续当前 Web Agent 对话）：\n{body}"
